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
from scripts.mail import compose, detect_default_mail_handler
from scripts.publisher import publish_assets
from scripts.recipients import load_recipients
from scripts.config import (
    ASSETS_DIR, DIST_DIR, DROP_DIR, MERIDIAN_TEMPLATE,
    ORIGINAL_TEMPLATE, PROJECT_ROOT, TITLE, get_default_repo,
)
from scripts.docx_parser import ImageRef, parse
from scripts.image_handler import (
    extract_embedded, ingest_drop_folder, issue_dir, to_raw_url,
)
from scripts.inliner import inline
from scripts.manifest import load_manifest, write_manifest
from scripts.renderer import attach_image_urls, render
from scripts.text_utils import sanitize_subject
from scripts.validator import report, validate

RECIPIENTS_PATH = PROJECT_ROOT / "recipients.txt"


@dataclass(frozen=True)
class BuildResult:
    """Return value of `_build_pipeline` -- replaces `(int, str)` tuple."""
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


def _friendly_used(used: str) -> str:
    """Translate the compose() return code into a human sentence."""
    if used == "outlook":
        return "Email draft opened in Outlook desktop."
    if used.startswith("default:") and "fallback-from-outlook" in used:
        return ("Outlook didn't open -- the newsletter is on your "
                "clipboard and a blank draft is open in your default "
                "email app. Click in the body and press Ctrl+V (Mac: Cmd+V).")
    if used.startswith("default:apple_mail"):
        return "Email draft opened in Apple Mail."
    if used.startswith("default:thunderbird"):
        return "Email draft opened in Thunderbird."
    if used.startswith("default:browser"):
        return ("Email draft opened in your browser-based mail client. "
                "The newsletter is on your clipboard -- press Ctrl+V "
                "in the message body.")
    if used.startswith("default:"):
        return ("Email draft opened in your default email app. "
                "The newsletter is on your clipboard -- press Ctrl+V "
                "in the message body.")
    return f"Email draft opened via: {used}"


def _subject_from_masthead(issue: int, masthead) -> str:
    """Build the email subject from an already-parsed masthead.

    Runs the issue line through `sanitize_subject` so Word-pasted
    invisibles (ZWSP, NBSP, BOM, RLO, ...) never reach the wire --
    otherwise the inbox preview displays one string while logs/audit
    trail show another.
    """
    issue_line = (masthead.issue_line or "") if masthead else ""
    issue_line = sanitize_subject(issue_line)
    if issue_line:
        return f"{TITLE} — {issue_line}"
    return f"{TITLE} — Issue {issue}"


def _build_pipeline(input_path: Path, issue: int, *,
                    validate_remote: bool) -> BuildResult:
    """Run the build pipeline. Returns a `BuildResult`."""
    out_html = DIST_DIR / f"issue-{issue}.html"
    DIST_DIR.mkdir(parents=True, exist_ok=True)

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
        click.echo(click.style(
            "Validation failed -- no file written. Fix the issues "
            "above and re-run.", fg="red"))
        return BuildResult(1, subject, out_html)

    # 8) Write -- only reached when validation passes.
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


def _subject_for(issue: int, input_path: Path | None = None) -> str:
    """Build the email subject line.

    Resolution order:
      1. The manifest written by `_build_pipeline` (cheap; one JSON read).
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
def compose_cmd(issue: int, input_path: str | None, backend: str):
    """Open the rendered email as a draft in your default email client."""
    out = DIST_DIR / f"issue-{issue}.html"
    if not out.exists():
        click.echo(f"Not found: {out}. Run `build` first.", err=True)
        sys.exit(1)
    html = out.read_text(encoding="utf-8")
    subject = _subject_for(issue, Path(input_path) if input_path else None)
    recipients = load_recipients(RECIPIENTS_PATH)
    bcc = "; ".join(recipients) or None
    handler = detect_default_mail_handler()
    if handler.is_outlook_desktop and backend in ("auto", "outlook"):
        click.echo(
            "Opening Outlook (this can take up to 30 seconds the first "
            "time; please do not click anywhere)..."
        )
    used = compose(html, subject=subject, backend=backend,
                   preview_path=out, bcc=bcc)
    click.echo(_friendly_used(used))
    click.echo(f"Subject: {subject}")
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
def all_cmd(input_path: str, issue: int, no_compose: bool, backend: str):
    """Run the full pipeline: build -> publish -> compose draft email."""
    asset_dir = issue_dir(ASSETS_DIR, issue)
    asset_dir.mkdir(parents=True, exist_ok=True)
    # Build first to populate assets/, then publish, then re-validate remotely.
    result = _build_pipeline(
        Path(input_path), issue, validate_remote=False)
    if result.exit_code != 0:
        sys.exit(result.exit_code)
    subject = result.subject
    try:
        sha = publish_assets(issue, push=True)
        if sha:
            click.echo(f"Pushed assets — commit {sha[:8]}")
    except Exception as e:
        click.echo(f"Publish skipped: {e}", err=True)

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
    handler = detect_default_mail_handler()
    if handler.is_outlook_desktop and backend in ("auto", "outlook"):
        click.echo(
            "Opening Outlook (this can take up to 30 seconds the first "
            "time; please do not click anywhere)..."
        )
    try:
        used = compose(html, subject=subject, backend=backend,
                       preview_path=out, bcc=bcc)
        click.echo(_friendly_used(used))
        click.echo(f"Subject: {subject}")
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
