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
from scripts.config import (
    ASSETS_DIR, DEFAULT_REPO, DIST_DIR, DROP_DIR, MERIDIAN_TEMPLATE,
    ORIGINAL_TEMPLATE, PROJECT_ROOT,
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


@cli.command("all")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True))
@click.option("--issue", required=True, type=int)
def all_cmd(input_path: str, issue: int):
    """Run the full pipeline: publish-images → build → preview."""
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
    # Open preview
    out = DIST_DIR / f"issue-{issue}.html"
    if out.exists():
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    cli()
