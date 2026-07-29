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
    ComposeOutcome, compose, detect_default_mail_handler, image_mode_key,
    resolve_image_mode, select_backend,
)
from scripts.publisher import publish_assets
from scripts.recipients import load_recipients
from scripts.config import (
    ASSETS_DIR, DIST_DIR, DROP_DIR, MERIDIAN_TEMPLATE,
    ORIGINAL_TEMPLATE, PROJECT_ROOT, TITLE,
    default_safe_output_dir, get_default_repo, is_writable_location,
)
from scripts.docx_parser import ImageRef, Masthead, parse
from scripts.image_handler import (
    extract_embedded, ingest_drop_folder, issue_dir, to_raw_url,
)
from scripts.inliner import inline
from scripts.manifest import load_manifest, write_manifest
from scripts.renderer import attach_image_urls, render
from scripts.subject import subject_from_masthead
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
    if used.backend == "eml":
        return ("Draft file written next to the preview (issue-N.eml) "
                "and handed to your default email app. If it didn't "
                "open by itself, double-click that .eml file -- it is "
                "a ready-to-send draft with the photos already inside.")
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


def _resolve_output_dir(user_choice: str | None) -> Path | None:
    """Resolve where to write `dist/` and `assets/` for this run.

    If the user passed `--output-dir`, that wins (and we probe-write
    it; an unwritable explicit choice is a hard error so they know
    immediately rather than silently falling back).

    If the user did NOT pass `--output-dir`, we check whether the
    toolkit folder accepts writes. If yes (the conventional case),
    return None so `_build_pipeline` keeps using `DIST_DIR` /
    `ASSETS_DIR` next to the script.

    If the toolkit folder is read-only (macOS Downloads sandbox is
    the production-bug case), redirect to
    `~/Documents/Meridian-Newsletter/` and tell the editor.
    Round-17 production-bug fix.
    """
    if user_choice is not None:
        chosen = Path(user_choice).expanduser().resolve()
        if not is_writable_location(chosen):
            click.echo(click.style(
                f"ERROR: --output-dir {chosen} is not writable. "
                "Pick a different location, or omit the flag to let "
                "the toolkit auto-pick a safe one.", fg="red"))
            sys.exit(2)
        click.echo(f"Output directory: {chosen}")
        return chosen

    if is_writable_location(PROJECT_ROOT):
        return None  # use DIST_DIR / ASSETS_DIR as before

    # Auto-fallback for the macOS Downloads-sandbox / read-only-mount
    # case. Tell the editor so they know where to look for the file.
    safe = default_safe_output_dir()
    click.echo(click.style(
        "Note: the toolkit folder is read-only (this can happen on "
        "macOS when the ZIP is run from `Downloads`, or when the "
        "folder lives on a read-only drive). Outputs will be saved "
        f"under: {safe}", fg="yellow"))
    click.echo(
        "Tip: to silence this notice, move the toolkit folder to a "
        "writable location (e.g. ~/Documents) and re-run, or pass "
        "--output-dir explicitly."
    )
    return safe


def _image_mode_blurb(image_mode: str | None) -> str | None:
    """Plain-English line about how photos will travel.

    Round-13 architect HIGH 2 + UX L2: both `compose` and `all` print
    the same confirmation, and the wording avoids jargon ("CID",
    "publish-images") that means nothing to a 50-ish editor at a
    medical school.

    Returns None when `image_mode` is None (legitimate -- no compose
    step ran) so the caller suppresses the line. Round-16 python
    MEDIUM: log a warning on an *unexpected* (non-None, non-cid,
    non-url) value -- the helper still returns None to keep the
    output clean, but a future caller passing an invalid mode will
    leave a trace instead of silently disappearing.
    """
    if image_mode == "cid":
        return ("Photos will be attached inside the email itself "
                "(no upload to GitHub needed for this send).")
    if image_mode == "url":
        return ("Photos will be loaded by recipients from the public "
                "GitHub host (raw.githubusercontent.com).")
    if image_mode is not None:
        log.warning(
            "Unexpected image_mode %r passed to _image_mode_blurb -- "
            "no user-facing photo-handling line will be printed. "
            "Expected: 'cid', 'url', or None.",
            image_mode,
        )
    return None


def _subject_from_masthead(issue: int, masthead: Masthead | None) -> str:
    """Build the email subject from an already-parsed masthead.

    Thin delegate to `scripts.subject.subject_from_masthead`, which is
    the single source of truth shared with the browser build. Two
    implementations of "what is this issue's subject line?" would
    eventually disagree, and the subject is what recipients see in
    their inbox preview *and* what the manifest records for the audit
    trail -- a mismatch between those two is exactly the class of bug
    `sanitize_subject` was added to prevent.
    """
    return subject_from_masthead(issue, masthead)


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
                    validate_remote: bool,
                    output_dir: Path | None = None) -> BuildResult:
    """Run the build pipeline. Returns a `BuildResult`.

    `output_dir`, if given, replaces `DIST_DIR` for the rendered HTML
    AND `ASSETS_DIR` for image extraction. Useful when the toolkit
    folder is read-only (macOS Downloads sandbox -- round-17
    production bug) or the editor wants outputs elsewhere.
    """
    if output_dir is not None:
        dist_dir = output_dir / "dist"
        # Note: assets/ MUST stay next to the toolkit when URL mode is
        # active (publish-images pushes to the toolkit's git repo).
        # In CID mode the assets dir is purely local-cache, so it's
        # safe to redirect. The CID-vs-URL decision happens later in
        # all_cmd; here we redirect both consistently and let the
        # publish step error out cleanly if URL mode is chosen on a
        # redirected layout.
        assets_dir = output_dir / "assets"
    else:
        dist_dir = DIST_DIR
        assets_dir = ASSETS_DIR
    out_html = dist_dir / f"issue-{issue}.html"

    # 1) Parse DOCX
    newsletter = parse(input_path)
    log.info("Parsed %d sections", len(newsletter.sections))

    # Round-17 production bug: if the parser produced ZERO sections
    # (both strict + lenient fallback found no body content), the
    # resulting email would be empty. Fail loudly so the editor sees
    # the problem in the launcher console BEFORE Outlook opens a
    # blank draft. The lenient fallback now handles arbitrary DOCX
    # files, so this branch fires only on truly empty / malformed
    # documents.
    if not newsletter.sections:
        click.echo(click.style(
            "ERROR: no content was extracted from your Word file. "
            "This usually means the file is empty, password-protected, "
            "or has a format the toolkit can't read. Open the .docx "
            "in Microsoft Word, confirm there's actual text/tables in "
            "the body (not just header/footer), save, and try again.",
            fg="red"))
        return BuildResult(1, "", out_html)

    # 2) Extract embedded images + ingest drop folder
    asset_dir = issue_dir(assets_dir, issue)
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
    dist_dir.mkdir(parents=True, exist_ok=True)
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
@click.option("--output-dir", "output_dir", default=None,
              type=click.Path(file_okay=False, resolve_path=True),
              help=("Where to write the rendered HTML and extracted "
                    "images. Default: next to the toolkit. Use this "
                    "if the toolkit folder is read-only (macOS "
                    "Downloads sandbox) or you want outputs elsewhere "
                    "(e.g. ~/Documents/Meridian-Newsletter)."))
def build_cmd(input_path: str, issue: int, no_remote_check: bool,
              output_dir: str | None):
    """Convert a filled DOCX into a polished HTML email."""
    out_dir = _resolve_output_dir(output_dir)
    result = _build_pipeline(
        Path(input_path), issue,
        validate_remote=not no_remote_check,
        output_dir=out_dir,
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
@click.option("--output-dir", "output_dir", default=None,
              type=click.Path(file_okay=False, resolve_path=True),
              help="Where the HTML was written (must match `build`'s "
                   "--output-dir). Default: next to the toolkit.")
def preview_cmd(issue: int, output_dir: str | None):
    """Open the rendered HTML in the default browser."""
    dist_dir = (
        Path(output_dir) / "dist" if output_dir else DIST_DIR
    )
    out = dist_dir / f"issue-{issue}.html"
    if not out.exists():
        click.echo(f"Not found: {out}", err=True)
        sys.exit(1)
    webbrowser.open(out.as_uri())


def _subject_from_path(issue: int, input_path: Path | None = None,
                       *, assets_dir: Path | None = None) -> str:
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

    `assets_dir` overrides the default `ASSETS_DIR` for the manifest
    lookup -- needed when `--output-dir` redirected the build's
    asset_dir to e.g. `~/Documents/Meridian-Newsletter/assets/`.
    """
    asset_dir = issue_dir(assets_dir or ASSETS_DIR, issue)
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
@click.option("--backend",
              type=click.Choice(["auto", "outlook", "default", "eml"]),
              default="auto",
              help="Override mail-client detection. `eml` writes a "
                   "ready-to-send draft file next to the preview "
                   "(dist/issue-N.eml) with the photos embedded, and "
                   "opens it -- no clipboard, no paste.")
@click.option("--image-mode", type=click.Choice(["auto", "url", "cid"]),
              default="auto",
              help=("`auto` (default): CID for Outlook desktop and for "
                    "`--backend=eml`, URL for everything else. `url`: "
                    "force URL hosting via raw.githubusercontent.com. "
                    "`cid`: force MIME inline attachments (needs "
                    "`--backend=outlook` or `--backend=eml`)."))
@click.option("--output-dir", "output_dir", default=None,
              type=click.Path(file_okay=False, resolve_path=True),
              help="Where `build` wrote the HTML (must match `build`'s "
                   "--output-dir). Default: next to the toolkit.")
def compose_cmd(issue: int, input_path: str | None, backend: str,
                image_mode: str, output_dir: str | None):
    """Open the rendered email as a draft in your default email client."""
    if output_dir is not None:
        dist_dir = Path(output_dir) / "dist"
        assets_dir = Path(output_dir) / "assets"
    else:
        dist_dir = DIST_DIR
        assets_dir = ASSETS_DIR
    out = dist_dir / f"issue-{issue}.html"
    if not out.exists():
        click.echo(f"Not found: {out}. Run `build` first.", err=True)
        sys.exit(1)
    html = out.read_text(encoding="utf-8")
    subject = _subject_from_path(
        issue, Path(input_path) if input_path else None,
        assets_dir=assets_dir)
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
        image_mode, handler, backend=image_mode_key(chosen),
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
            issue_dir(assets_dir, issue)
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
@click.option("--backend",
              type=click.Choice(["auto", "outlook", "default", "eml"]),
              default="auto",
              help="Override mail-client detection for the compose step. "
                   "`eml` writes a ready-to-send draft file "
                   "(dist/issue-N.eml) with the photos embedded, and "
                   "opens it -- no clipboard, no paste.")
@click.option("--image-mode", type=click.Choice(["auto", "url", "cid"]),
              default="auto",
              help=("`auto` (default): pick the best mode for your mail "
                    "client. Outlook desktop (or `--backend=eml`) -> CID "
                    "(photos attached inline via MIME, no GitHub "
                    "publishing needed). Anything else -> URL (photos "
                    "hosted on GitHub). `cid`: force CID (needs "
                    "`--backend=outlook` or `--backend=eml`). `url`: "
                    "force URL (uploads photos via publish-images first)."))
@click.option("--output-dir", "output_dir", default=None,
              type=click.Path(file_okay=False, resolve_path=True),
              help=("Where to write the rendered HTML and extracted "
                    "images. Default: next to the toolkit, with an "
                    "auto-fallback to ~/Documents/Meridian-Newsletter "
                    "if the toolkit folder is read-only (macOS "
                    "Downloads sandbox). Pass an explicit path to "
                    "override."))
def all_cmd(input_path: str, issue: int, no_compose: bool, backend: str,
            image_mode: str, output_dir: str | None):
    """Run the full pipeline: build -> publish -> compose draft email."""
    # Round-17: resolve the output dir up-front. Either explicit
    # (--output-dir), or auto-fallback to ~/Documents/Meridian-Newsletter
    # if the toolkit folder is read-only (macOS Downloads sandbox).
    out_dir_override = _resolve_output_dir(output_dir)
    # Phase 2 / round-13 architect M3 + round-15 architect HIGH 1 +
    # round-16 python MEDIUM (filesystem leak):
    # detect handler + resolve the SAME backend the dispatcher will
    # pick + resolve image mode + validate FEASIBILITY before any
    # side effects (the build step writes to dist/, the publish step
    # pushes to GitHub, AND `assets/issue-N/` mkdir leaves a directory
    # behind even when validation rejects the run -- round-16 moved
    # the mkdir AFTER validation so a failed early-exit leaves no
    # filesystem state on the editor's machine).
    #
    # Round-13 used `handler.is_outlook_desktop` as the proxy for "is
    # the chosen backend Outlook?" -- which diverged from
    # `select_backend()` in two cases the round-15 audit caught:
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
        image_mode, handler, backend=image_mode_key(chosen),
    )
    if resolved_image_mode == "cid" and not chosen.supports_inline_images:
        # Ask the backend whether it can embed photos rather than
        # testing `chosen.name != "outlook"` here: that string test was
        # the round-15 bug in a different disguise, and it would also
        # have silently rejected the `.eml` backend, which can embed
        # photos perfectly well.
        # Round-16 python LOW: surface the user-facing CLI label
        # ("default" / "outlook"), not the internal backend ID
        # ("clipboard_mailto") which is opaque to a non-developer.
        friendly_backend = (
            "default" if chosen.name == "clipboard_mailto" else chosen.name
        )
        click.echo(
            "ERROR: --image-mode=cid needs a backend that can put the "
            "photos inside the email. The toolkit selected "
            f"--backend={friendly_backend} for this run "
            f"(detected mail app: {handler.name}). Use "
            "--backend=eml to get a ready-to-send draft file with the "
            "photos embedded, --image-mode=url for the hosted-photo "
            "path, or --image-mode=auto to let the toolkit pick.",
            err=True,
        )
        sys.exit(2)

    # Validation passed -- now create the asset dir and run the
    # build. Anything that creates state on disk lives below this line.
    effective_assets = (
        out_dir_override / "assets" if out_dir_override else ASSETS_DIR
    )
    asset_dir = issue_dir(effective_assets, issue)
    asset_dir.mkdir(parents=True, exist_ok=True)

    # Build first to populate assets/.
    result = _build_pipeline(
        Path(input_path), issue, validate_remote=False,
        output_dir=out_dir_override,
    )
    if result.exit_code != 0:
        sys.exit(result.exit_code)
    subject = result.subject

    if resolved_image_mode == "url":
        # URL mode: photos must be reachable at `raw.githubusercontent.com`
        # before recipients open the email, so push them now.
        if out_dir_override is not None:
            click.echo(click.style(
                "Note: --output-dir was set, so the published "
                "photos live OUTSIDE the toolkit's git checkout. "
                "URL mode requires them inside the git tree to "
                "push to GitHub. Skipping publish-images. Either "
                "use --image-mode=cid (Outlook), or run without "
                "--output-dir.", fg="yellow"))
        else:
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

    effective_dist = (
        out_dir_override / "dist" if out_dir_override else DIST_DIR
    )
    out = effective_dist / f"issue-{issue}.html"
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
