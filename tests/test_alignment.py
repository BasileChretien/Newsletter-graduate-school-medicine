"""Paragraph alignment ("justification") survives from Word to the email.

Reported from the field: the justified body text of a real issue came
out ragged-right. `paragraph_to_html` read runs, links and pictures but
never `w:jc`, so every paragraph fell back to the stylesheet's left
alignment. In the issue that prompted this, 106 of 125 paragraphs were
justified (両端揃え, the default for Word set up for Japanese) and the
photo captions were centred -- all of it was lost.

What is pinned here:
  * how the effective alignment is RESOLVED -- direct formatting, then
    the paragraph style and its `basedOn` chain, then the document
    defaults -- and how Word's values map onto an allowlist of CSS
    values;
  * that both parsers carry it on body paragraphs, bullet items and
    table cells;
  * that it survives rendering and CSS inlining, and that a picture in
    a centred paragraph is centred too.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
import pytest
from bs4 import BeautifulSoup
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image

from scripts.docx_parser import (
    BodyParagraph,
    BulletList,
    Masthead,
    Newsletter,
    Section,
    TableBlock,
    _parse_lenient,
    paragraph_alignment,
    paragraph_to_html,
    parse,
)
from scripts.inliner import inline
from scripts.renderer import attach_image_urls, render
from scripts.webapp import build_from_bytes


# ---------- helpers ----------
def _set_raw_jc(paragraph, value: str) -> None:
    """Write `<w:jc w:val=value>` directly, bypassing python-docx's enum.

    The enum has no member for `start`, `end` or the kashida variants,
    and cannot express a hostile value at all -- which is exactly what
    a hand-edited or third-party DOCX can contain.
    """
    ppr = paragraph._p.get_or_add_pPr()
    for old in ppr.findall(qn("w:jc")):
        ppr.remove(old)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), value)
    ppr.append(jc)


def _set_doc_default_jc(document, value: str) -> None:
    styles = document.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        defaults = OxmlElement("w:docDefaults")
        styles.insert(0, defaults)
    ppr_default = defaults.find(qn("w:pPrDefault"))
    if ppr_default is None:
        ppr_default = OxmlElement("w:pPrDefault")
        defaults.append(ppr_default)
    ppr = ppr_default.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        ppr_default.append(ppr)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), value)
    ppr.append(jc)


# ---------- resolution ----------
@pytest.mark.parametrize("value, expected", [
    ("both", "justify"),
    ("distribute", "justify"),        # 均等割り付け
    ("mediumKashida", "justify"),
    ("highKashida", "justify"),
    ("lowKashida", "justify"),
    ("thaiDistribute", "justify"),
    ("center", "center"),
    ("right", "right"),
    ("end", "right"),
    ("left", ""),
    ("start", ""),
    ("numTab", ""),
    ("bogus", ""),
    # Never echoed into a style attribute: only allowlisted values out.
    ("both;background:url(https://evil.example/x)", ""),
    ("", ""),
])
def test_word_values_map_to_an_allowlist_of_css_values(value, expected):
    d = docx.Document()
    p = d.add_paragraph("Text.")
    _set_raw_jc(p, value)
    assert paragraph_alignment(p) == expected


@pytest.mark.parametrize("enum_value, expected", [
    (WD_ALIGN_PARAGRAPH.JUSTIFY, "justify"),
    (WD_ALIGN_PARAGRAPH.DISTRIBUTE, "justify"),
    (WD_ALIGN_PARAGRAPH.CENTER, "center"),
    (WD_ALIGN_PARAGRAPH.RIGHT, "right"),
    (WD_ALIGN_PARAGRAPH.LEFT, ""),
])
def test_alignment_set_through_word_ui_equivalents(enum_value, expected):
    d = docx.Document()
    p = d.add_paragraph("Text.")
    p.alignment = enum_value
    assert paragraph_alignment(p) == expected


def test_unaligned_paragraph_resolves_to_empty():
    d = docx.Document()
    assert paragraph_alignment(d.add_paragraph("Text.")) == ""


def test_alignment_is_inherited_through_the_style_chain():
    d = docx.Document()
    base = d.styles.add_style("Justified Base", WD_STYLE_TYPE.PARAGRAPH)
    base.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    child = d.styles.add_style("Child Of Justified", WD_STYLE_TYPE.PARAGRAPH)
    child.base_style = base
    p = d.add_paragraph("Inherited.", style=child)
    assert paragraph_alignment(p) == "justify"


def test_direct_formatting_overrides_the_style():
    d = docx.Document()
    st = d.styles.add_style("Justified", WD_STYLE_TYPE.PARAGRAPH)
    st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p = d.add_paragraph("Override.", style=st)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    assert paragraph_alignment(p) == ""


def test_alignment_falls_back_to_document_defaults():
    d = docx.Document()
    _set_doc_default_jc(d, "both")
    assert paragraph_alignment(d.add_paragraph("Default.")) == "justify"


def test_a_basedon_cycle_does_not_hang():
    """A style `basedOn` itself (hand-edited XML) must terminate."""
    d = docx.Document()
    st = d.styles.add_style("Loop", WD_STYLE_TYPE.PARAGRAPH)
    based_on = OxmlElement("w:basedOn")
    based_on.set(qn("w:val"), st.style_id)
    st.element.append(based_on)
    assert paragraph_alignment(d.add_paragraph("Loop.", style=st)) == ""


# ---------- parsers carry it ----------
def _make_issue(path: Path) -> Path:
    """A minimal template-shaped document: masthead table, one section."""
    d = docx.Document()
    d.add_table(rows=1, cols=2)          # masthead -- skipped by the parser
    d.add_paragraph("1. News")
    body = d.add_paragraph("A justified paragraph that runs long enough.")
    body.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    caption = d.add_paragraph("Left: a centred photo caption.")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph("A plain left paragraph with a full stop.")

    for text, align in (("First bullet item.", WD_ALIGN_PARAGRAPH.JUSTIFY),
                        ("Second bullet item.", None)):
        item = d.add_paragraph(text, style="List Paragraph")
        if align is not None:
            item.alignment = align

    t = d.add_table(rows=2, cols=2)
    for cell, align in ((t.cell(0, 0), WD_ALIGN_PARAGRAPH.CENTER),
                        (t.cell(0, 1), None)):
        cell.paragraphs[0].text = "Header."
        if align is not None:
            cell.paragraphs[0].alignment = align
    uniform = t.cell(1, 0)
    uniform.paragraphs[0].text = "Justified one."
    uniform.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    second = uniform.add_paragraph("Justified two.")
    second.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    mixed = t.cell(1, 1)
    mixed.paragraphs[0].text = "Centred."
    mixed.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    mixed.add_paragraph("Justified.").alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    d.save(str(path))
    return path


@pytest.fixture
def issue_blocks(tmp_path: Path):
    news = parse(_make_issue(tmp_path / "issue-7.docx"))
    assert len(news.sections) == 1
    return news.sections[0].blocks


def test_strict_parse_keeps_body_paragraph_alignment(issue_blocks):
    paras = [b for b in issue_blocks if isinstance(b, BodyParagraph)]
    assert [(b.html[:10], b.align) for b in paras] == [
        ("A justifie", "justify"),
        ("Left: a ce", "center"),
        ("A plain le", ""),
    ]


def test_strict_parse_keeps_bullet_item_alignment(issue_blocks):
    (bullets,) = [b for b in issue_blocks if isinstance(b, BulletList)]
    assert bullets.aligns == ("justify", "")
    assert len(bullets.aligns) == len(bullets.items)


def test_table_cells_keep_a_uniform_alignment_and_drop_a_mixed_one(
    issue_blocks,
):
    """A cell has one `text-align`. When its paragraphs disagree there is
    no single right answer, so the cell falls back to the default rather
    than guessing."""
    (table,) = [b for b in issue_blocks if isinstance(b, TableBlock)]
    assert table.aligns == (("center", ""), ("justify", ""))
    assert [len(r) for r in table.aligns] == [len(r) for r in table.rows]


def test_lenient_parse_keeps_alignment(tmp_path: Path):
    d = docx.Document()
    p = d.add_paragraph("No numbered headings here, just justified text.")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    item = d.add_paragraph("A centred bullet.", style="List Paragraph")
    item.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.save(str(tmp_path / "user.docx"))

    (section,) = _parse_lenient(docx.Document(str(tmp_path / "user.docx")))
    body = [b for b in section.blocks if isinstance(b, BodyParagraph)]
    bullets = [b for b in section.blocks if isinstance(b, BulletList)]
    assert body[0].align == "justify"
    assert bullets[0].aligns == ("center",)


def test_blocks_built_without_alignment_still_construct():
    """Existing callers pass only the old fields."""
    assert BodyParagraph(html="x").align == ""
    assert BulletList(items=("a",)).aligns == ()
    assert TableBlock(rows=(("a",),), has_header=False).aligns == ()


# ---------- rendering ----------
def _newsletter(*blocks) -> Newsletter:
    return Newsletter(
        masthead=Masthead("MERIDIAN", "", "", "VOL. 1 | ISSUE NO. 1 | MAY 2026"),
        sections=(Section(number=1, title="News", blocks=tuple(blocks)),),
    )


def _style_of(html: str, tag: str, text: str) -> str:
    """Whitespace-free inline style of the `tag` element whose text is `text`."""
    soup = BeautifulSoup(html, "html.parser")
    (el,) = [e for e in soup.find_all(tag) if e.get_text(strip=True) == text]
    return re.sub(r"\s+", "", el.get("style", ""))


def test_body_paragraph_alignment_survives_render_and_inlining():
    html = inline(render(_newsletter(
        BodyParagraph(html="Justified words.", align="justify"),
        BodyParagraph(html="Left words."),
    )))
    assert "text-align:justify" in _style_of(html, "p", "Justified words.")
    # Left is the default: no declaration, so no bytes towards Gmail's clip.
    assert "text-align" not in _style_of(html, "p", "Left words.")


def test_bullet_item_alignment_is_rendered():
    html = inline(render(_newsletter(
        BulletList(items=("Centred item.", "Plain item."),
                   aligns=("center", "")),
    )))
    assert "text-align:center" in _style_of(html, "td", "Centred item.")
    assert "text-align" not in _style_of(html, "td", "Plain item.")


def test_data_table_cell_alignment_beats_the_stylesheet():
    """`table.data th` is `text-align:left` in styles.css; the document's
    own alignment has to win after inlining."""
    html = inline(render(_newsletter(
        TableBlock(rows=(("H1", "H2"), ("a", "b")), has_header=True,
                   aligns=(("center", ""), ("", "right"))),
    )))
    assert "text-align:center" in _style_of(html, "th", "H1")
    assert "text-align:left" in _style_of(html, "th", "H2")
    assert "text-align:right" in _style_of(html, "td", "b")
    assert "text-align" not in _style_of(html, "td", "a")


def test_highlight_card_and_layout_cell_alignment_is_rendered():
    html = inline(render(_newsletter(
        TableBlock(rows=(("Card one.", "", "Card two."),), has_header=False,
                   aligns=(("justify", "", ""),)),
        TableBlock(rows=(("Layout left.", "Layout right."),),
                   has_header=False, aligns=(("", "right"),)),
    )))
    assert "text-align:justify" in _style_of(html, "td", "Card one.")
    assert "text-align" not in _style_of(html, "td", "Card two.")
    assert "text-align:right" in _style_of(html, "td", "Layout right.")


def test_short_or_missing_aligns_render_as_default():
    """Blocks built by hand (tests, a notebook, a future caller) may carry
    fewer alignments than cells. That must render, not raise."""
    html = inline(render(_newsletter(
        BulletList(items=("One.", "Two."), aligns=("center",)),
        TableBlock(rows=(("x", "y"), ("z", "w")), has_header=True,
                   aligns=(("right",),)),
    )))
    assert "text-align" not in _style_of(html, "td", "Two.")
    assert "text-align:right" in _style_of(html, "th", "x")
    assert "text-align" not in _style_of(html, "td", "w")


def test_attach_image_urls_preserves_alignment():
    out = attach_image_urls(_newsletter(
        BodyParagraph(html="p", align="justify"),
        BulletList(items=("i",), aligns=("center",)),
        TableBlock(rows=(("c",),), has_header=False, aligns=(("right",),)),
    ), {})
    body, bullets, table = out.sections[0].blocks
    assert (body.align, bullets.aligns, table.aligns) == (
        "justify", ("center",), (("right",),))


# ---------- pictures ----------
@pytest.mark.parametrize("align, margin", [
    (WD_ALIGN_PARAGRAPH.CENTER, "margin:0 auto;"),
    (WD_ALIGN_PARAGRAPH.RIGHT, "margin:0 0 0 auto;"),
    (WD_ALIGN_PARAGRAPH.LEFT, "margin:0;"),
    (None, "margin:0;"),
])
def test_picture_follows_its_paragraph_alignment(tmp_path: Path, align, margin):
    """Pictures are `display:block`, and a block is not moved by its
    parent's `text-align` in Gmail or Apple Mail -- only by auto margins.
    Outlook's Word engine ignores those margins but honours `text-align`,
    so a centred photo needs both."""
    png = tmp_path / "photo.png"
    Image.new("RGB", (40, 20), "white").save(png)
    d = docx.Document()
    p = d.add_paragraph()
    if align is not None:
        p.alignment = align
    p.add_run().add_picture(str(png))
    html = paragraph_to_html(p)
    assert "<img" in html
    assert margin in html


# ---------- end to end ----------
def test_web_build_keeps_justification_end_to_end(tmp_path: Path):
    """The whole pipeline -- parse, render, inline, CID rewrite, standalone
    -- through the same entry point the browser build calls."""
    src = _make_issue(tmp_path / "issue-7.docx")
    result = build_from_bytes(src.read_bytes(), issue=7)
    for doc in (result.html, result.standalone_html):
        assert "text-align:justify" in _style_of(
            doc, "p", "A justified paragraph that runs long enough.")
        assert "text-align:center" in _style_of(
            doc, "p", "Left: a centred photo caption.")
