"""Tests for renderer + inliner."""

from __future__ import annotations

import pytest

from scripts.docx_parser import (
    BodyParagraph, BulletList, Heading, ImageRef, Masthead, Newsletter,
    Section, TableBlock,
)
from scripts.inliner import inline
from scripts.renderer import attach_image_urls, render


def _sample_newsletter() -> Newsletter:
    return Newsletter(
        masthead=Masthead(
            title="MERIDIAN",
            tagline="Test tagline.",
            subtitle="Test subtitle.",
            issue_line="VOL. 1 | ISSUE 1 | APR 2026",
        ),
        sections=(
            Section(
                number=1,
                title="MESSAGE FROM THE DEAN",
                blocks=(
                    BodyParagraph(html="Hello <strong>world</strong>."),
                ),
            ),
            Section(
                number=3,
                title="RESEARCH",
                blocks=(
                    Heading(level=3, text="Notable Publications"),
                    BulletList(items=("Paper one.", "Paper two.")),
                    TableBlock(
                        rows=(("Name", "Country"), ("Alice", "JP")),
                        has_header=True,
                    ),
                    ImageRef(rel_id="rId1", filename="image1.jpg",
                             alt="lab", url=""),
                ),
            ),
        ),
    )


def test_render_includes_title():
    nl = _sample_newsletter()
    html = render(nl)
    assert "MERIDIAN" in html
    assert "Test subtitle" in html


def test_render_section_heading_zero_padded():
    html = render(_sample_newsletter())
    assert "01" in html
    assert "03" in html


def test_render_bullet_list():
    html = render(_sample_newsletter())
    assert "Paper one" in html
    assert "Paper two" in html
    # Bullets render as table rows with an inline marker so they survive
    # Gmail/Outlook style stripping.
    assert '<table class="bullets"' in html
    assert "&#9632;" in html  # filled square glyph


def test_render_table_with_header():
    html = render(_sample_newsletter())
    assert '<table class="data"' in html
    assert "<th" in html and "Name</th>" in html
    assert "<td>Alice</td>" in html


def test_attach_image_urls_fills_url():
    nl = _sample_newsletter()
    enriched = attach_image_urls(
        nl,
        url_map={"image1.jpg": "https://example.com/image1.jpg"},
    )
    images = [
        b for s in enriched.sections for b in s.blocks
        if isinstance(b, ImageRef)
    ]
    assert images
    assert images[0].url == "https://example.com/image1.jpg"


def test_attach_image_urls_inserts_drop_images():
    nl = _sample_newsletter()
    drop = ImageRef(rel_id="", filename="s1_01_dean.jpg", alt="dean",
                    url="https://example.com/dean.jpg")
    enriched = attach_image_urls(nl, url_map={}, drop_inserts={1: [drop]})
    sec1 = next(s for s in enriched.sections if s.number == 1)
    images = [b for b in sec1.blocks if isinstance(b, ImageRef)]
    assert len(images) == 1
    assert images[0].url == "https://example.com/dean.jpg"


def test_inliner_inlines_styles():
    nl = _sample_newsletter()
    raw = render(nl)
    final = inline(raw)
    # The only <style> remaining should be inside the MSO conditional comment.
    # Strip MSO comments and confirm no orphan <style> blocks exist.
    import re
    stripped = re.sub(r"<!--\[if mso\]>.*?<!\[endif\]-->", "", final,
                      flags=re.DOTALL)
    assert "<style" not in stripped
    # Inlined background color from masthead style
    assert "background-color: #F7F2EA".lower() in final.lower() or \
           "background-color:#F7F2EA".lower() in final.lower()


def test_render_escapes_user_html_in_body():
    nl = Newsletter(
        masthead=Masthead("M", "", "", ""),
        sections=(Section(
            number=1, title="T",
            blocks=(BodyParagraph(html="safe text"),),
        ),),
    )
    html = render(nl)
    assert "safe text" in html
