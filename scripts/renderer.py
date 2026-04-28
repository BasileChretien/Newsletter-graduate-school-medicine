"""Render a parsed Newsletter into HTML via Jinja2."""

from __future__ import annotations

import re
from dataclasses import replace
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.config import (
    DEFAULT_REPO,
    LOGO_REL,
    TEMPLATES_DIR,
)
from scripts.docx_parser import (
    BodyParagraph,
    BulletList,
    ImageRef,
    Newsletter,
    Section,
    TableBlock,
)


# Pattern emitted by docx_parser._drawing_to_img for inline images.
_MEDIA_SENTINEL_RE = re.compile(r'media://([^"\'\s>]+)')


def _resolve_media(html: str, url_map: dict[str, str]) -> str:
    """Replace `media://filename` sentinels with their public URLs."""
    if not html or "media://" not in html:
        return html

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        return url_map.get(name, m.group(0))

    return _MEDIA_SENTINEL_RE.sub(_sub, html)


# The Nagoya template wraps every placeholder in <em> italic. Once an
# editor types real content, those <em> wrappers persist into the email
# and make the whole list/table read like grey-italic placeholder text.
# Strip <em>...</em> wrappers from rendered body / bullet / cell content.
# We DO NOT strip <strong> -- bold is still meaningful.
_EM_WRAPPER_RE = re.compile(r"</?em>", re.IGNORECASE)


def _strip_em(html: str) -> str:
    return _EM_WRAPPER_RE.sub("", html) if html else html


def _issue_line_filter(text: str) -> str:
    """Color the pipes in the issue line gold."""
    parts = re.split(r"(\s*\|\s*)", text)
    out = []
    for part in parts:
        if "|" in part:
            out.append(f'<span class="pipe">{escape(part)}</span>')
        else:
            out.append(escape(part))
    return "".join(out)


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["issue_line"] = _issue_line_filter
    env.tests["highlights_block"] = _is_highlights_block_filter
    return env


def _is_highlights_table(block: TableBlock) -> bool:
    """Detect a 3-column layout table where the middle column is empty
    on every row — that's the Featured Highlights spacer pattern."""
    if block.has_header or not block.rows:
        return False
    if not all(len(row) == 3 for row in block.rows):
        return False
    return all(not row[1].strip() for row in block.rows)


def attach_image_urls(newsletter: Newsletter, url_map: dict[str, str],
                      drop_inserts: dict[int, list[ImageRef]] | None = None) -> Newsletter:
    """Return a new Newsletter with image URLs filled in.

    `url_map` maps embedded image filenames (basename) to public URLs.
    Walks every block and resolves `media://filename` sentinels emitted by
    the parser when it encountered inline images in paragraphs / table
    cells. `drop_inserts` maps section number → list of ImageRef to append
    at the end of that section's blocks (drop-folder images).
    """
    drop_inserts = drop_inserts or {}
    new_sections: list[Section] = []
    for section in newsletter.sections:
        new_blocks = []
        for block in section.blocks:
            if isinstance(block, BodyParagraph):
                html = _strip_em(_resolve_media(block.html, url_map))
                new_blocks.append(replace(block, html=html))
            elif isinstance(block, BulletList):
                new_items = tuple(
                    _strip_em(_resolve_media(item, url_map))
                    for item in block.items
                )
                new_blocks.append(replace(block, items=new_items))
            elif isinstance(block, TableBlock):
                new_rows = tuple(
                    tuple(_strip_em(_resolve_media(c, url_map)) for c in row)
                    for row in block.rows
                )
                new_blocks.append(replace(block, rows=new_rows))
            elif isinstance(block, ImageRef):
                url = block.url or url_map.get(block.filename, "")
                new_blocks.append(replace(block, url=url))
            else:
                new_blocks.append(block)
        # Append drop-folder images (already carry a url).
        for img in drop_inserts.get(section.number, []):
            new_blocks.append(img)
        new_sections.append(replace(section, blocks=tuple(new_blocks)))
    return replace(newsletter, sections=tuple(new_sections))


def _is_highlights_block_filter(block) -> bool:
    """Jinja-callable version of _is_highlights_table."""
    return isinstance(block, TableBlock) and _is_highlights_table(block)


def render(newsletter: Newsletter, *, logo_url: str | None = None) -> str:
    """Render a Newsletter to HTML.

    All image content embedded by the editor in Word — including the Dean
    photo — is detected by the parser as `<img src="media://…">` sentinels
    and resolved during `attach_image_urls`. Nothing further is needed
    here besides the standalone brand logo (which is referenced by URL,
    not extracted from the DOCX).
    """
    env = make_env()
    template = env.get_template("newsletter.html.j2")
    if logo_url is None:
        logo_url = DEFAULT_REPO.raw_url(LOGO_REL)
    return template.render(
        masthead=newsletter.masthead,
        sections=newsletter.sections,
        logo_url=logo_url,
        # expose dataclass classes so the partial can do isinstance-style checks
        BulletList=BulletList,
        TableBlock=TableBlock,
        ImageRef=ImageRef,
    )


__all__ = ["render", "attach_image_urls", "make_env"]
