"""CLI entrypoint for the MERIDIAN newsletter pipeline.

Examples:
    python build_newsletter.py build-template
    python build_newsletter.py build --input filled.docx --issue 1
    python build_newsletter.py publish-images --issue 1
    python build_newsletter.py preview --issue 1
    python build_newsletter.py all --input filled.docx --issue 1
"""

from __future__ import annotations

import logging
import sys
import webbrowser
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import click

from scripts import build_template as bt
from scripts.mail import (
    ComposeOutcome, compose, detect_default_mail_handler,
    resolve_image_mode, select_backend,
)
from scripts.publisher import publish_assets
from scripts.recipients import load_recipients
from scripts.config import (
    ASSETS_DIR, DIST_DIR, DROP_DIR, MERIDIAN_TEMPLATE,
    ORIGINAL_TEMPLATE, PROJECT_ROOT, TITLE, get_default_repo,
)
from scripts.docx_parser import ImageRef, Masthead, parse
from scripts.image_handler import (
    extract_embedded, ingest_drop_folder, issue_dir, to_raw_url,
)
from scripts.inliner import inline
from scripts.manifest import load_manifest, write_manifest
from scripts.renderer import attach_image_urls, render
from scripts.text_utils import sanitize_subject
from scripts.validator import report, validate

RECIPIENTS_PATH = PROJECT_ROOT / "recipients.txt"

# Subject-length thresholds for the soft warning. Round-9 Email M1:
#   * 50 chars   -- inbox-list previews truncate around here on Outlook
#                   desktop / Gmail web; recipients only see the first
#                   ~50 chars in their preview.
#   * 78 chars   -- historical RFC 5322 wrap point; modern SMTP no
#                   longer enforces it but Proofpoint / Mimecast
#                   spam-score this threshold.
# We warn at 50 (gentle nudge to keep preview-readable subjects) and
# warn more strongly at 78. Never block -- subject choice belongs to
# the editor.
_SUBJECT_PREVIEW_LIMIT_CHARS = 50
_SUBJECT_SPAM_LIMIT_CHARS = 78


@dataclass(frozen=True)
class BuildResult:
    """Return value of `_build_pipeline`.

    Fields:
      * `exit_code`  -- 0 on success, non-zero when validation hard-blocks.
      * `subject`    -- sanitized email subject line (NFKC, no invisibles).
      * `html_path`  -- intended location of the rendered HTML. Only
                        guaranteed to exist on disk when `exit_code == 0`.
    """
    exit_code: int
    subject: str
    html_path: Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


@click.group()
def cli():
    """MERIDIAN newsletter pipeline — build the template, then convert
    a filled DOCX into a polished HTML email."""


@cli.command("build-template")
@click.option("--source", default=str(ORIGINAL_TEMPLATE), type=click.Path(),
              help="Original DOCX to restyle.")
@click.option("--output", default=str(MERIDIAN_TEMPLATE), type=click.Path(),
              help="Where to write the modernized template.")
def build_template_cmd(source: str, output: str):
    """Generate the modernized MERIDIAN template DOCX."""
    out = bt.build(Path(source), Path(output))
    click.echo(f"Built: {out}")


def _friendly_used(used: ComposeOutcome) -> str:
    """Translate the compose() outcome into a human sentence.

    Accepts a `ComposeOutcome` dataclass; matches on `.backend`,
    `.handler_kind`, and `.is_fallback` exclusively (no `str(used)`
    or `.startswith` -- those shims emit DeprecationWarning).
    """
    if used.is_fallback and used.fell_back_from == "outlook":
        return ("Outlook didn't open -- the newsletter is on your "
                "clipboard and a blank draft is open in your default "
                "email app. Click in the body and press Ctrl+V (Mac: Cmd+V).")
    if used.backend == "outlook":
        return "Email draft opened in Outlook desktop."
    if used.handler_kind == "apple_mail":
        return "Email draft opened in Apple Mail."
    if used.handler_kind == "thunderbird":
        return "Email draft opened in Thunderbird."
    if used.handler_kind == "browser":
        return ("Email draft opened in your browser-based mail client. "
                "The newsletter is on your clipboard -- press Ctrl+V "
                "in the message body.")
    if used.backend == "clipboard_mailto":
        return ("Email draft opened in your default email app. "
                "The newsletter is on your clipboard -- press Ctrl+V "
                "in the message body.")
    return f"Email draft opened via: {used}"


def _image_mode_blurb(image_mode: str | None) -> str | None:
    """Plain-English line about how photos will travel.

    Round-13 architect HIGH 2 + UX L2: both `compose` and `all` print
    the same confirmation, and the wording avoids jargon ("CID",
    "publish-images") that means nothing to a 50-ish editor at a
    medical school.
    """
    if image_mode == "cid":
        return ("Photos will be attached inside the email itself "
                "(no upload to GitHub needed for this send).")
    if image_mode == "url":
        return ("Photos will be loaded by recipients from the public "
                "GitHub host (raw.githubusercontent.com).")
    return None


def _subject_from_masthead(issue: int, masthead: Masthead | None) -> str:
    """Build the email subject from an already-parsed masthead.

    Runs the issue line through `sanitize_subject` so Word-pasted
    invisibles (ZWSP, NBSP, BOM, RLO, ...) never reach the wire --
    otherwise the inbox preview displays one string while logs/audit
    trail show another.

    Defends against a non-string `issue_line` (schema drift / bug)
    by falling back to the generic subject -- a TypeError here used
    to short-circuit the validate-before-write guard, so we keep
    subject derivation total.
    """
    try:
        issue_line = (masthead.issue_line or "") if masthead else ""
        issue_line = sanitize_subject(issue_line)
    except (AttributeError, TypeError) as e:
        log.warning(
            "Could not derive subject from masthead (%s); "
            "falling back to generic subject.", e)
        issue_line = ""
    if issue_line:
        return f"{TITLE} — {issue_line}"
    return f"{TITLE} — Issue {issue}"


def _delete_stale_html(out_html: Path) -> None:
    """Remove a previous-run HTML file from disk.

    Called when validation fails so the editor doesn't accidentally
    double-click last month's `dist/issue-N.html` thinking it's the
    current build. Best-effort: any OSError is logged and ignored.
    """
    if not out_html.exists():
        return
    try:
        out_html.unlink()
        log.info("Removed stale %s (validation failed; no fresh "
                 "HTML to replace it).", out_html.name)
    except OSError as e:
        log.warning("Could not remove stale %s: %s", out_html, e)


def _build_pipeline(input_path: Path, issue: int, *,
                    validate_remote: bool) -> BuildResult:
    """Run the build pipeline. Returns a `BuildResult`."""
    out_html = DIST_DIR / f"issue-{issue}.html"

    # 1) Parse DOCX
    newsletter = parse(input_path)
    log.info("Parsed %d sections", len(newsletter.sections))

    # 2) Extract embedded images + ingest drop folder
    asset_dir = issue_dir(ASSETS_DIR, issue)
    embedded = extract_embedded(input_path, asset_dir)
    drops = ingest_drop_folder(DROP_DIR, asset_dir)
    log.info("Embedded images: %d, drop-folder images: %d",
             len(embedded), len(drops))

    # 3) Build URL map for embedded images (by basename)
    url_map = {
        name: to_raw_url(p, PROJECT_ROOT, get_default_repo())
        for name, p in embedded.items()
    }

    # 4) Build drop-image inserts grouped by section
    drop_inserts: dict[int, list[ImageRef]] = defaultdict(list)
    for d in drops:
        url = to_raw_url(d.dst_path, PROJECT_ROOT, get_default_repo())
        drop_inserts[d.section].append(ImageRef(
            rel_id="", filename=d.dst_path.name, alt=d.slug, url=url,
        ))

    # 5) Inject URLs
    enriched = attach_image_urls(newsletter, url_map, drop_inserts)

    # 6) Render
    raw_html = render(enriched)
    final_html = inline(raw_html)
    subject = _subject_from_masthead(issue, newsletter.masthead)

    # 7) Validate FIRST -- a hard-block from `validate()` (e.g. unfilled
    # masthead `VOL. XX`) must NOT leave a stale openable HTML on disk
    # that the editor double-clicks and pastes into Outlook. So we
    # validate the in-memory HTML before persisting anything.
    result = validate(final_html, check_remote=validate_remote)
    click.echo(report(result))
    if not result.ok:
        # Remove last issue's HTML so the editor doesn't double-click
        # it thinking it's the new one. Validation failed, so there's
        # nothing fresh to leave on disk.
        _delete_stale_html(out_html)
        click.echo(click.style(
            "Validation failed -- no file written. Any older "
            f"{out_html.name} from a previous run was removed so you "
            "don't accidentally open it. Scroll up to the lines that "
            "start with \"ERROR:\", fix those in your Word file, then "
            "re-run the launcher (re-running is always safe -- it "
            "rebuilds from scratch).", fg="red"))
        return BuildResult(1, subject, out_html)

    # Soft warnings on subject length. Two thresholds:
    #   * > 78 chars  -- historic RFC 5322 wrap + spam-filter heuristic.
    #   * > 50 chars  -- inbox preview truncation in Outlook / Gmail web.
    # The wording suggests the most common fix (abbreviate MONTH YEAR)
    # because that's the typical overflow source for this newsletter
    # template (round-9 UX M4).
    n = len(subject)
    if n > _SUBJECT_SPAM_LIMIT_CHARS:
        click.echo(click.style(
            f"Heads up: subject is {n} characters "
            f"(> {_SUBJECT_SPAM_LIMIT_CHARS}). Many spam filters "
            "score long subjects higher, and inbox-list previews on "
            "most clients will truncate it. Tip: shorten the masthead "
            "issue line -- the subject is built from "
            "\"VOL. X | ISSUE NO. Y | MONTH YEAR\". Common quick wins: "
            "abbreviate the month (\"MAR 2026\"), drop a subtitle, or "
            "use shorter Roman numerals.",
            fg="yellow"))
    elif n > _SUBJECT_PREVIEW_LIMIT_CHARS:
        click.echo(click.style(
            f"Note: subject is {n} characters "
            f"(> {_SUBJECT_PREVIEW_LIMIT_CHARS}). Outlook desktop and "
            "Gmail web typically truncate inbox-list previews around "
            "50 chars, so recipients may only see the first half. "
            "If that's a concern, shorten the masthead issue line -- "
            "the subject is built from \"VOL. X | ISSUE NO. Y | "
            "MONTH YEAR\". Quickest win: abbreviate the month "
            "(\"MAR 2026\" instead of \"MARCH 2026\").",
            fg="yellow"))

    # 8) Write -- only reached when validation passes. mkdir is here
    # rather than at the top of the pipeline so a hard-block doesn't
    # leave behind an empty `dist/` (cosmetic, but matches the
    # "no stale state on failure" intent).
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out_html.write_text(final_html, encoding="utf-8")
    click.echo(f"Wrote: {out_html}")

    # 9) Manifest -- audit trail for what was published when. A manifest
    # write failure is non-fatal: the HTML is already on disk and
    # validation already passed.
    try:
        manifest = write_manifest(
            issue=issue,
            asset_dir=asset_dir,
            source_docx=input_path,
            subject=subject,
            output_html=out_html,
        )
        log.debug("Manifest: %s files (sha %s...)",
                  manifest.file_count, manifest.docx_sha256[:8])
    except (OSError, ValueError, TypeError) as e:
        log.warning("Could not write manifest: %s", e)

    return BuildResult(0, subject, out_html)


@cli.command("build")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True))
@click.option("--issue", required=True, type=int)
@click.option("--no-remote-check", is_flag=True,
              help="Skip HEAD requests to remote image URLs.")
def build_cmd(input_path: str, issue: int, no_remote_check: bool):
    """Convert a filled DOCX into a polished HTML email."""
    result = _build_pipeline(
        Path(input_path), issue,
        validate_remote=not no_remote_check,
    )
    sys.exit(result.exit_code)


@cli.command("publish-images")
@click.option("--issue", required=True, type=int)
@click.option("--no-push", is_flag=True, help="Commit but don't push.")
def publish_images_cmd(issue: int, no_push: bool):
    """Commit (and push) /assets/issue-N/ so raw URLs go live."""
    sha = publish_assets(issue, push=not no_push)
    if sha:
        click.echo(f"Published assets for issue {issue} — commit {sha[:8]}")
    else:
        click.echo("No changes to publish.")


@cli.command("preview")
@click.option("--issue", required=True, type=int)
def preview_cmd(issue: int):
    """Open the rendered HTML in the default browser."""
    out = DIST_DIR / f"issue-{issue}.html"
    if not out.exists():
        click.echo(f"Not found: {out}", err=True)
        sys.exit(1)
    webbrowser.open(out.as_uri())


def _subject_from_path(issue: int, input_path: Path | None = None) -> str:
    """Build the email subject line from a DOCX path or manifest cache.

    Resolution order:
      1. The manifest written by `_build_pipeline` (cheap; one JSON read).
         Older manifests pre-dating the subject sanitizer are re-sanitized
         on read so a stale invisibles-laden subject doesn't escape via
         the cached path.
      2. Re-parse the DOCX masthead (only when no manifest exists, e.g.
         a `compose --issue N` invocation against an issue that was
         built on another machine).
      3. Generic fallback `MERIDIAN — Issue N`.
    """
    asset_dir = issue_dir(ASSETS_DIR, issue)
    manifest = load_manifest(asset_dir)
    if manifest is not None and manifest.subject:
        # Re-sanitize: an older manifest may have been written before
        # the subject sanitizer existed, so we don't want a stale
        # invisible-laden subject to escape via the cached path.
        return sanitize_subject(manifest.subject)

    if input_path is not None and input_path.exists():
        try:
            nl = parse(input_path)
            return _subject_from_masthead(issue, nl.masthead)
        except (OSError, ValueError, TypeError) as e:
            log.debug("Could not derive subject from %s: %s", input_path, e)

    return f"{TITLE} — Issue {issue}"


@cli.command("detect-mail")
def detect_mail_cmd():
    """Show which email client the toolkit will use."""
    h = detect_default_mail_handler()
    click.echo(f"Default mail handler: {h.name}")
    click.echo(f"Kind:                 {h.kind}")
    if h.raw_id:
        click.echo(f"OS identifier:        {h.raw_id}")
    if h.is_outlook_desktop:
        click.echo("-> Outlook desktop will receive a fully populated draft.")
    else:
        click.echo("-> HTML will be copied to your clipboard; the default "
                   "handler opens with subject pre-filled. Paste with Ctrl+V.")


@cli.command("compose")
@click.option("--issue", required=True, type=int)
@click.option("--input", "input_path", default=None,
              type=click.Path(exists=True),
              help="DOCX used to derive a richer subject line.")
@click.option("--backend", type=click.Choice(["auto", "outlook", "default"]),
              default="auto",
              help="Override mail-client detection.")
@click.option("--image-mode", type=click.Choice(["auto", "url", "cid"]),
              default="auto",
              help=("`auto` (default): CID for Outlook desktop, URL for "
                    "everything else. `url`: force URL hosting via "
                    "raw.githubusercontent.com. `cid`: force MIME inline "
                    "attachments (Outlook only)."))
def compose_cmd(issue: int, input_path: str | None, backend: str,
                image_mode: str):
    """Open the rendered email as a draft in your default email client."""
    out = DIST_DIR / f"issue-{issue}.html"
    if not out.exists():
        click.echo(f"Not found: {out}. Run `build` first.", err=True)
        sys.exit(1)
    html = out.read_text(encoding="utf-8")
    subject = _subject_from_path(
        issue, Path(input_path) if input_path else None)
    recipients = load_recipients(RECIPIENTS_PATH)
    bcc = "; ".join(recipients) or None
    handler = detect_default_mail_handler()
    # Resolve image mode HERE so we can decide whether to pass
    # asset_dir, and so we surface the SAME plain-language confirmation
    # that `all` prints. Round-13 architect HIGH 1 + HIGH 2 +
    # round-15 architect HIGH 1: pass the chosen-backend identity, not
    # the raw user flag, so the helper agrees with what compose() will
    # actually dispatch to.
    chosen = select_backend(backend, handler)
    resolved_image_mode = resolve_image_mode(
        image_mode, handler,
        backend=("outlook" if chosen.name == "outlook" else "default"),
    )
    if chosen.name == "outlook":
        click.echo(
            "Opening Outlook (this can take up to 30 seconds the first "
            "time; please wait -- clicking other windows may cancel "
            "the draft)..."
        )
    used = compose(
        html, subject=subject, backend=backend,
        preview_path=out, bcc=bcc,
        image_mode=resolved_image_mode,
        asset_dir=(
            issue_dir(ASSETS_DIR, issue)
            if resolved_image_mode == "cid"
            else None
        ),
    )
    click.echo(_friendly_used(used))
    click.echo(f"Subject: {subject}")
    blurb = _image_mode_blurb(used.image_mode)
    if blurb is not None:
        click.echo(blurb)
    if recipients:
        click.echo(
            f"BCC pre-filled with {len(recipients)} recipient(s) "
            "from recipients.txt"
        )


@cli.command("all")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True))
@click.option("--issue", required=True, type=int)
@click.option("--no-compose", is_flag=True,
              help="Skip opening the email draft at the end.")
@click.option("--backend", type=click.Choice(["auto", "outlook", "default"]),
              default="auto",
              help="Override mail-client detection for the compose step.")
@click.option("--image-mode", type=click.Choice(["auto", "url", "cid"]),
              default="auto",
              help=("`auto` (default): pick the best mode for your mail "
                    "client. Outlook desktop -> CID (photos attached "
                    "inline via MIME, no GitHub publishing needed). "
                    "Anything else -> URL (photos hosted on GitHub). "
                    "`cid`: force CID (Outlook only). `url`: force URL "
                    "(uploads photos via publish-images first)."))
def all_cmd(input_path: str, issue: int, no_compose: bool, backend: str,
            image_mode: str):
    """Run the full pipeline: build -> publish -> compose draft email."""
    asset_dir = issue_dir(ASSETS_DIR, issue)
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Phase 2 / round-13 architect M3 + round-15 architect HIGH 1:
    # detect handler + resolve the SAME backend the dispatcher will
    # pick + resolve image mode + validate FEASIBILITY before any
    # side effects (the build step writes to dist/, the publish step
    # pushes to GitHub).
    #
    # Round-13 used `handler.is_outlook_desktop` as the proxy for "is
    # the chosen backend Outlook?" -- which diverged from
    # `_select_backend()` in two cases the round-15 audit caught:
    #   (a) Windows box where Outlook is the OS default but
    #       `OutlookBackend.is_available()` returns False (partial
    #       pywin32 / COM init failure) -> dispatcher falls back to
    #       clipboard, but `is_outlook_desktop` is still True ->
    #       round-13 predicate incorrectly accepts `cid` mode and
    #       compose() then raises after the build/publish-skip
    #       side-effects ran.
    #   (b) `--backend=default --image-mode=cid` on an Outlook box ->
    #       same half-published failure (round-14 noted this; round-15
    #       fixes it together with (a) by switching to chosen.name).
    handler = detect_default_mail_handler()
    chosen = select_backend(backend, handler)
    resolved_image_mode = resolve_image_mode(
        image_mode, handler,
        backend=("outlook" if chosen.name == "outlook" else "default"),
    )
    if resolved_image_mode == "cid" and chosen.name != "outlook":
        click.echo(
            "ERROR: --image-mode=cid is only supported with the "
            "Outlook desktop backend. The toolkit selected "
            f"{chosen.name!r} for this run "
            f"(handler kind: {handler.kind}). Use --image-mode=url "
            "for the non-Outlook path (photos hosted on GitHub), or "
            "--image-mode=auto to let the toolkit pick.",
            err=True,
        )
        sys.exit(2)

    # Build first to populate assets/.
    result = _build_pipeline(
        Path(input_path), issue, validate_remote=False)
    if result.exit_code != 0:
        sys.exit(result.exit_code)
    subject = result.subject

    if resolved_image_mode == "url":
        # URL mode: photos must be reachable at `raw.githubusercontent.com`
        # before recipients open the email, so push them now.
        try:
            sha = publish_assets(issue, push=True)
            if sha:
                click.echo(f"Pushed assets — commit {sha[:8]}")
        except Exception as e:
            click.echo(f"Publish skipped: {e}", err=True)
    else:
        # CID mode: photos travel as MIME parts inside the email
        # itself; no public hosting needed. Skip publish-images
        # entirely. This is what removes the GitHub-account
        # requirement from the editor's onboarding flow.
        # Round-13 UX L2: jargon-free wording. The user-facing
        # confirmation (after compose) is in `_image_mode_blurb()`;
        # this is the operational note explaining what just got
        # skipped, kept short and plain.
        click.echo(
            "Skipping the GitHub upload step -- photos will travel "
            "inside the email itself."
        )

    out = DIST_DIR / f"issue-{issue}.html"
    if not out.exists():
        return

    if no_compose:
        webbrowser.open(out.as_uri())
        return

    html = out.read_text(encoding="utf-8")
    # `subject` is already populated from the build step's masthead
    # parse -- no need to re-parse the DOCX here.
    recipients = load_recipients(RECIPIENTS_PATH)
    bcc = "; ".join(recipients) or None
    # Round-15: key the "Opening Outlook" hint off the actually-chosen
    # backend, not handler+raw-flag. Avoids printing the hint when
    # Outlook is the OS default but `is_available()` returned False
    # so the dispatcher already fell through to clipboard.
    if chosen.name == "outlook":
        click.echo(
            "Opening Outlook (this can take up to 30 seconds the first "
            "time; please wait -- clicking other windows may cancel "
            "the draft)..."
        )
    try:
        used = compose(
            html, subject=subject, backend=backend,
            preview_path=out, bcc=bcc,
            image_mode=resolved_image_mode,
            asset_dir=asset_dir if resolved_image_mode == "cid" else None,
        )
        click.echo(_friendly_used(used))
        click.echo(f"Subject: {subject}")
        # Round-13 architect HIGH 2: same plain-English line in both
        # `compose` and `all`. `used.image_mode` is the resolved value
        # from `compose()` (so an Outlook auto-fallback to clipboard
        # correctly reports "url" here, not the CID we asked for).
        blurb = _image_mode_blurb(used.image_mode)
        if blurb is not None:
            click.echo(blurb)
        if recipients:
            click.echo(
                f"BCC pre-filled with {len(recipients)} recipient(s) "
                "from recipients.txt"
            )
    except Exception as e:
        click.echo(f"Could not open email draft ({e}). Opening preview instead.",
                   err=True)
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    cli()
