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
from dataclasses import replace
from pathlib import Path

import click

from scripts import build_template as bt
from scripts.composer import compose as compose_email, detect_default_mail_handler
from scripts.config import (
    ASSETS_DIR, DEFAULT_REPO, DIST_DIR, DROP_DIR, MERIDIAN_TEMPLATE,
    ORIGINAL_TEMPLATE, PROJECT_ROOT, TITLE,
)
from scripts.docx_parser import ImageRef, parse
from scripts.image_handler import (
    extract_embedded, ingest_drop_folder, issue_dir, to_raw_url,
)
from scripts.inliner import inline
from scripts.renderer import attach_image_urls, render
from scripts.validator import report, validate

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


def _build_pipeline(input_path: Path, issue: int, *, validate_remote: bool):
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
        name: to_raw_url(p, PROJECT_ROOT, DEFAULT_REPO)
        for name, p in embedded.items()
    }

    # 4) Build drop-image inserts grouped by section
    drop_inserts: dict[int, list[ImageRef]] = defaultdict(list)
    for d in drops:
        url = to_raw_url(d.dst_path, PROJECT_ROOT, DEFAULT_REPO)
        drop_inserts[d.section].append(ImageRef(
            rel_id="", filename=d.dst_path.name, alt=d.slug, url=url,
        ))

    # 5) Inject URLs
    enriched = attach_image_urls(newsletter, url_map, drop_inserts)

    # 6) Render
    raw_html = render(enriched)
    final_html = inline(raw_html)

    # 7) Write
    out_html.write_text(final_html, encoding="utf-8")
    click.echo(f"Wrote: {out_html}")

    # 8) Validate
    result = validate(final_html, check_remote=validate_remote)
    click.echo(report(result))
    if not result.ok:
        click.echo(click.style("Validation failed.", fg="red"))
        return 1
    return 0


@cli.command("build")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True))
@click.option("--issue", required=True, type=int)
@click.option("--no-remote-check", is_flag=True,
              help="Skip HEAD requests to remote image URLs.")
def build_cmd(input_path: str, issue: int, no_remote_check: bool):
    """Convert a filled DOCX into a polished HTML email."""
    code = _build_pipeline(
        Path(input_path), issue,
        validate_remote=not no_remote_check,
    )
    sys.exit(code)


@cli.command("publish-images")
@click.option("--issue", required=True, type=int)
@click.option("--no-push", is_flag=True, help="Commit but don't push.")
def publish_images_cmd(issue: int, no_push: bool):
    """Commit (and push) /assets/issue-N/ so raw URLs go live."""
    from scripts.publisher import publish_assets
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
    """Build the email subject line. Pulls the issue line from the DOCX
    masthead when available, otherwise falls back to a generic format."""
    if input_path is not None and input_path.exists():
        try:
            from scripts.docx_parser import parse as _parse
            nl = _parse(input_path)
            issue_line = nl.masthead.issue_line.strip()
            if issue_line:
                return f"{TITLE} — {issue_line}"
        except Exception:
            pass
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
    used = compose_email(html, subject=subject, backend=backend,
                         preview_path=out)
    click.echo(f"Email draft opened via: {used}")
    click.echo(f"Subject: {subject}")


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
    from scripts.publisher import publish_assets
    asset_dir = issue_dir(ASSETS_DIR, issue)
    asset_dir.mkdir(parents=True, exist_ok=True)
    # Build first to populate assets/, then publish, then re-validate remotely.
    code = _build_pipeline(Path(input_path), issue, validate_remote=False)
    if code != 0:
        sys.exit(code)
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
    subject = _subject_for(issue, Path(input_path))
    try:
        used = compose_email(html, subject=subject, backend=backend,
                             preview_path=out)
        click.echo(f"Email draft opened via: {used}")
        click.echo(f"Subject: {subject}")
    except Exception as e:
        click.echo(f"Could not open email draft ({e}). Opening preview instead.",
                   err=True)
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    cli()
