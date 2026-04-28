"""Render a parsed Newsletter into HTML via Jinja2."""

from __future__ import annotations

import re
from dataclasses import replace
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scripts.config import (
    DEAN_PHOTO_PLACEHOLDER,
    DEAN_REL,
    DEFAULT_REPO,
    LOGO_REL,
    TEMPLATES_DIR,
)
from scripts.docx_parser import (
    BulletList,
    ImageRef,
    Newsletter,
    Section,
    TableBlock,
)


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
    return env


def attach_image_urls(newsletter: Newsletter, url_map: dict[str, str],
                      drop_inserts: dict[int, list[ImageRef]] | None = None) -> Newsletter:
    """Return a new Newsletter with image URLs filled in.

    `url_map` maps embedded image filenames (basename) to public URLs.
    `drop_inserts` maps section number → list of ImageRef to append at the
    end of that section's blocks (drop-folder images).
    """
    drop_inserts = drop_inserts or {}
    new_sections: list[Section] = []
    for section in newsletter.sections:
        new_blocks = []
        for block in section.blocks:
            if isinstance(block, ImageRef):
                url = url_map.get(block.filename, "")
                new_blocks.append(replace(block, url=url))
            else:
                new_blocks.append(block)
        # Append drop-folder images (already carry a url).
        for img in drop_inserts.get(section.number, []):
            new_blocks.append(img)
        new_sections.append(replace(section, blocks=tuple(new_blocks)))
    return replace(newsletter, sections=tuple(new_sections))


def _replace_dean_placeholder(newsletter: Newsletter, dean_url: str) -> Newsletter:
    """Inject the Dean photo into Section 1's left layout-table cell.

    Two cases handled:
      1. Cell still contains the literal '[ Photo ]' placeholder (raw original
         template) — replace the placeholder text with an <img>.
      2. Cell no longer has the placeholder (Meridian template embedded the
         photo as a Word picture, which the text-only parser drops) — prepend
         the <img> to the first cell of the first table in Section 1.
    """
    if not dean_url:
        return newsletter
    img_html = (
        f'<img src="{dean_url}" alt="Dean of the Graduate School of Medicine" '
        f'style="display:block;width:140px;max-width:100%;height:auto;'
        f'margin:0 0 8px 0;border:2px solid #8B1A1F;" />'
    )
    new_sections = []
    for section in newsletter.sections:
        if section.number != 1:
            new_sections.append(section)
            continue
        new_blocks = []
        injected = False
        for block in section.blocks:
            if isinstance(block, TableBlock):
                new_rows = list(block.rows)
                if not injected and new_rows:
                    first_row = list(new_rows[0])
                    if first_row:
                        if DEAN_PHOTO_PLACEHOLDER in first_row[0]:
                            first_row[0] = first_row[0].replace(
                                DEAN_PHOTO_PLACEHOLDER, img_html)
                        else:
                            first_row[0] = img_html + first_row[0]
                        new_rows[0] = tuple(first_row)
                        injected = True
                new_blocks.append(replace(block, rows=tuple(new_rows)))
            else:
                new_blocks.append(block)
        new_sections.append(replace(section, blocks=tuple(new_blocks)))
    return replace(newsletter, sections=tuple(new_sections))


def render(newsletter: Newsletter, *,
           logo_url: str | None = None,
           dean_url: str | None = None) -> str:
    env = make_env()
    template = env.get_template("newsletter.html.j2")
    if logo_url is None:
        logo_url = DEFAULT_REPO.raw_url(LOGO_REL)
    if dean_url is None:
        dean_url = DEFAULT_REPO.raw_url(DEAN_REL)
    enriched = _replace_dean_placeholder(newsletter, dean_url)
    return template.render(
        masthead=enriched.masthead,
        sections=enriched.sections,
        logo_url=logo_url,
        dean_url=dean_url,
        # expose dataclass classes so the partial can do isinstance-style checks
        BulletList=BulletList,
        TableBlock=TableBlock,
        ImageRef=ImageRef,
    )


__all__ = ["render", "attach_image_urls", "make_env"]
