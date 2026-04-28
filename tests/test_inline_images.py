"""Tests for inline image detection and media:// sentinel resolution."""

from __future__ import annotations

import re

import pytest

from scripts.config import MERIDIAN_TEMPLATE
from scripts.docx_parser import (
    BodyParagraph, Newsletter, Section, TableBlock, parse,
)
from scripts.renderer import _resolve_media, attach_image_urls


pytestmark_template = pytest.mark.skipif(
    not MERIDIAN_TEMPLATE.exists(),
    reason="MERIDIAN template not built yet",
)


# ---------- _resolve_media unit tests ----------
def test_resolve_media_swaps_known_filenames():
    html = '<img src="media://photo.jpg" alt="x">'
    out = _resolve_media(html, {"photo.jpg": "https://example.com/p.jpg"})
    assert "media://" not in out
    assert "https://example.com/p.jpg" in out


def test_resolve_media_leaves_unknown_intact():
    html = '<img src="media://missing.jpg">'
    out = _resolve_media(html, {})
    assert out == html


def test_resolve_media_no_op_when_no_sentinel():
    html = '<p>plain text</p>'
    assert _resolve_media(html, {"x.jpg": "https://x"}) == html


def test_resolve_media_handles_multiple_in_one_string():
    html = (
        '<img src="media://a.jpg"> text '
        '<img src="media://b.jpg">'
    )
    out = _resolve_media(html, {
        "a.jpg": "https://example.com/a.jpg",
        "b.jpg": "https://example.com/b.jpg",
    })
    assert out.count("https://example.com/a.jpg") == 1
    assert out.count("https://example.com/b.jpg") == 1
    assert "media://" not in out


# ---------- attach_image_urls integration ----------
def test_attach_image_urls_resolves_in_body_paragraphs():
    nl = Newsletter(
        masthead=type("M", (), {"title": "x", "tagline": "", "subtitle": "",
                                "issue_line": ""})(),
        sections=(Section(
            number=1, title="T",
            blocks=(BodyParagraph(html='See <img src="media://a.jpg">.'),),
        ),),
    )
    out = attach_image_urls(nl, {"a.jpg": "https://example.com/a.jpg"})
    rendered = out.sections[0].blocks[0].html
    assert "https://example.com/a.jpg" in rendered
    assert "media://" not in rendered


def test_attach_image_urls_resolves_in_table_cells():
    nl = Newsletter(
        masthead=type("M", (), {"title": "x", "tagline": "", "subtitle": "",
                                "issue_line": ""})(),
        sections=(Section(
            number=1, title="T",
            blocks=(TableBlock(
                rows=(('<img src="media://x.jpg">', "text"),),
                has_header=False,
            ),),
        ),),
    )
    out = attach_image_urls(nl, {"x.jpg": "https://example.com/x.jpg"})
    new_block = out.sections[0].blocks[0]
    assert "https://example.com/x.jpg" in new_block.rows[0][0]
    assert "media://" not in new_block.rows[0][0]


# ---------- Live parse on the Meridian template ----------
@pytestmark_template
def test_parse_meridian_template_detects_inline_images():
    nl = parse(MERIDIAN_TEMPLATE)
    found: list[tuple[int, str]] = []
    for sec in nl.sections:
        for block in sec.blocks:
            if isinstance(block, BodyParagraph):
                for m in re.finditer(r"media://([^\"'\s>]+)", block.html):
                    found.append((sec.number, m.group(1)))
            elif isinstance(block, TableBlock):
                for row in block.rows:
                    for cell in row:
                        for m in re.finditer(r"media://([^\"'\s>]+)", cell):
                            found.append((sec.number, m.group(1)))
    # Section 1 (Message from the Dean) must contain the dean photo.
    section1_imgs = [name for num, name in found if num == 1]
    assert section1_imgs, "Expected at least one inline image in Section 1"


@pytestmark_template
def test_parsed_inline_images_have_size_and_style():
    nl = parse(MERIDIAN_TEMPLATE)
    for sec in nl.sections:
        for block in sec.blocks:
            html = ""
            if isinstance(block, BodyParagraph):
                html = block.html
            elif isinstance(block, TableBlock):
                html = " ".join(c for row in block.rows for c in row)
            for img_tag in re.findall(r"<img[^>]+>", html):
                # Each inline <img> should carry style + sane media:// or http
                assert "style=" in img_tag
                assert ('media://' in img_tag or
                        img_tag.startswith('<img src="http'))
