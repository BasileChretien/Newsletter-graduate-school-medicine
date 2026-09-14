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

from scripts import docx_parser
from scripts.docx_parser import (
    BodyParagraph,
    BulletList,
    Masthead,
    Newsletter,
    Section,
    TableBlock,
    _parse_lenient,
    _table_to_block,
    paragraph_alignment,
    paragraph_to_html,
    parse,
)
from scripts.inliner import inline
from scripts.renderer import _align_at, attach_image_urls, render
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


def test_a_missing_style_falls_back_to_the_default_paragraph_style():
    """`w:pStyle` naming a style that does not exist -- a paragraph pasted
    from another document -- is laid out by Word with the default
    paragraph style, so it takes that style's alignment."""
    d = docx.Document()
    d.styles["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p = d.add_paragraph("Pasted from elsewhere.")
    p_style = OxmlElement("w:pStyle")
    p_style.set(qn("w:val"), "NoSuchStyle")
    p._p.get_or_add_pPr().insert(0, p_style)
    assert paragraph_alignment(p) == "justify"


def test_a_basedon_cycle_does_not_hang():
    """A style `basedOn` itself (hand-edited XML) must terminate."""
    d = docx.Document()
    st = d.styles.add_style("Loop", WD_STYLE_TYPE.PARAGRAPH)
    based_on = OxmlElement("w:basedOn")
    based_on.set(qn("w:val"), st.style_id)
    st.element.append(based_on)
    assert paragraph_alignment(d.add_paragraph("Loop.", style=st)) == ""


def test_each_style_is_resolved_once_per_document(monkeypatch):
    """Walking the style chain per cell made the 20,000-cell table cap ~4x
    slower to parse; it has to happen once per style, not per paragraph."""
    calls = []
    real = docx_parser._style_chain_jc
    monkeypatch.setattr(
        docx_parser, "_style_chain_jc",
        lambda styles, style_id: calls.append(style_id) or real(styles, style_id))
    d = docx.Document()
    for _ in range(40):
        d.add_paragraph("Normal paragraph.")
        d.add_paragraph("A list item.", style="List Paragraph")
    assert {paragraph_alignment(p) for p in d.paragraphs} == {""}
    assert sorted(calls, key=str) == sorted([None, "ListParagraph"], key=str)


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


# ---------- table styles ----------
# A table style can align text with no paragraph alignment at all: its own
# paragraph properties, and conditional formatting for the header row,
# first column, banded rows and so on (`w:tblStylePr`), switched on per
# table by `w:tblLook`. Several of Word's built-in table styles centre a
# header row exactly that way.
def _append_jc(parent, value: str) -> None:
    ppr = parent.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        parent.append(ppr)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), value)
    ppr.append(jc)


def _table_style(doc, name: str, *, base: str | None = None,
                 conditional: dict[str, str] | None = None, based_on=None):
    style = doc.styles.add_style(name, WD_STYLE_TYPE.TABLE)
    if based_on is not None:
        style.base_style = based_on
    if base is not None:
        _append_jc(style.element, base)
    for kind, value in (conditional or {}).items():
        pr = OxmlElement("w:tblStylePr")
        pr.set(qn("w:type"), kind)
        _append_jc(pr, value)
        style.element.append(pr)
    return style


_LOOK_FLAGS = ("firstRow", "lastRow", "firstColumn", "lastColumn",
               "noHBand", "noVBand")


def _set_look(table, **flags) -> None:
    """Replace `w:tblLook` with exactly these flags (all others "0")."""
    tbl_pr = table._tbl.tblPr
    for old in tbl_pr.findall(qn("w:tblLook")):
        tbl_pr.remove(old)
    look = OxmlElement("w:tblLook")
    for flag in _LOOK_FLAGS:
        look.set(qn(f"w:{flag}"), "1" if flags.get(flag) else "0")
    tbl_pr.append(look)


def _filled_table(doc, rows: int, cols: int, style=None, **look):
    """A table whose cell (r, c) reads `r{r}c{c}.`."""
    table = doc.add_table(rows=rows, cols=cols)
    if style is not None:
        table.style = style
    for r in range(rows):
        for c in range(cols):
            table.cell(r, c).text = f"r{r}c{c}."
    _set_look(table, **look)
    return table


def test_table_style_alignment_applies_to_its_cells():
    d = docx.Document()
    t = _filled_table(d, 2, 2, _table_style(d, "Centred Table", base="center"))
    assert _table_to_block(t).aligns == (("center", "center"),
                                         ("center", "center"))


def test_paragraph_style_and_direct_formatting_beat_the_table_style():
    d = docx.Document()
    justified = d.styles.add_style("Justified Cell", WD_STYLE_TYPE.PARAGRAPH)
    justified.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    t = _filled_table(d, 1, 3, _table_style(d, "Centred Table", base="center"))
    t.cell(0, 1).paragraphs[0].style = justified
    t.cell(0, 2).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    assert _table_to_block(t).aligns == (("center", "justify", ""),)


def test_table_style_beats_document_defaults():
    d = docx.Document()
    _set_doc_default_jc(d, "right")
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    assert _table_to_block(t).aligns == (("center",),)


@pytest.mark.parametrize("first_row, header", [(True, "center"),
                                               (False, "justify")])
def test_header_row_formatting_follows_tbllook(first_row, header):
    d = docx.Document()
    style = _table_style(d, "Header Table", base="both",
                         conditional={"firstRow": "center"})
    t = _filled_table(d, 3, 2, style, firstRow=first_row)
    aligns = _table_to_block(t).aligns
    assert aligns[0] == (header, header)
    assert aligns[1:] == (("justify", "justify"),) * 2


def test_legacy_hex_tbllook_enables_the_header_row():
    """Older files carry only `w:val`, a bitmask; 0x0020 is the first row."""
    d = docx.Document()
    style = _table_style(d, "Header Table", conditional={"firstRow": "center"})
    t = _filled_table(d, 2, 1, style)
    tbl_pr = t._tbl.tblPr
    for old in tbl_pr.findall(qn("w:tblLook")):
        tbl_pr.remove(old)
    legacy = OxmlElement("w:tblLook")
    legacy.set(qn("w:val"), "0020")
    tbl_pr.append(legacy)
    assert _table_to_block(t).aligns == (("center",), ("",))


def test_table_style_conditional_formatting_is_inherited_through_basedon():
    d = docx.Document()
    base = _table_style(d, "Base Table", base="center",
                        conditional={"firstRow": "right"})
    derived = _table_style(d, "Derived Table", based_on=base)
    t = _filled_table(d, 2, 1, derived, firstRow=True)
    assert _table_to_block(t).aligns == (("right",), ("center",))


def test_a_table_without_a_style_uses_the_default_table_style():
    d = docx.Document()
    defaults = [s for s in d.styles.element.findall(qn("w:style"))
                if s.get(qn("w:type")) == "table"
                and s.get(qn("w:default")) in ("1", "true", "on")]
    if defaults:
        default = defaults[0]
    else:
        default = _table_style(d, "Default Table").element
        default.set(qn("w:default"), "1")
    _append_jc(default, "right")
    t = _filled_table(d, 1, 1)
    for old in t._tbl.tblPr.findall(qn("w:tblStyle")):
        t._tbl.tblPr.remove(old)
    assert _table_to_block(t).aligns == (("right",),)


def test_last_row_and_first_last_column_formatting():
    """Corner cells are left out here: which condition wins where a row
    and a column meet is pinned separately."""
    d = docx.Document()
    style = _table_style(d, "Edges", conditional={
        "lastRow": "right", "firstCol": "center", "lastCol": "both"})
    t = _filled_table(d, 3, 3, style, lastRow=True, firstColumn=True,
                      lastColumn=True, noHBand=True, noVBand=True)
    aligns = _table_to_block(t).aligns
    assert aligns[0] == ("center", "", "justify")
    assert aligns[1] == ("center", "", "justify")
    assert aligns[2][1] == "right"


def test_hostile_table_style_values_are_dropped():
    d = docx.Document()
    style = _table_style(d, "Hostile", base="center;color:red",
                         conditional={"firstRow;x": "center"})
    t = _filled_table(d, 2, 1, style, firstRow=True)
    assert _table_to_block(t).aligns == (("",), ("",))


def test_picture_in_a_table_style_centred_cell_is_centred(tmp_path: Path):
    png = tmp_path / "photo.png"
    Image.new("RGB", (40, 20), "white").save(png)
    d = docx.Document()
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    t.cell(0, 0).paragraphs[0].add_run().add_picture(str(png))
    ((cell,),) = _table_to_block(t).rows
    assert "margin:0 auto;" in cell


# Word's own rules, where they differ from the letter of ECMA-376, as
# Microsoft documents them in [MS-OI29500].
def _set_style_band_sizes(style, *, row: int | None = None,
                          col: int | None = None) -> None:
    tbl_pr = style.element.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        style.element.append(tbl_pr)
    for axis, size in (("Row", row), ("Col", col)):
        if size is not None:
            el = OxmlElement(f"w:tblStyle{axis}BandSize")
            el.set(qn("w:val"), str(size))
            tbl_pr.append(el)


def _rows_col0(table) -> list[str]:
    return [row[0] for row in _table_to_block(table).aligns]


def test_where_a_row_meets_a_column_the_row_wins_unless_a_corner_is_set():
    """Word applies first/last column before first/last row, and corner
    cells after both; ECMA-376 lists the first two the other way round."""
    d = docx.Document()
    rows_win = _table_style(d, "Rows Win", conditional={
        "firstRow": "center", "firstCol": "right"})
    t = _filled_table(d, 2, 2, rows_win, firstRow=True, firstColumn=True)
    assert _table_to_block(t).aligns == (("center", "center"), ("right", ""))

    corner = _table_style(d, "Corner", conditional={
        "firstRow": "center", "firstCol": "right", "nwCell": "both"})
    t = _filled_table(d, 2, 2, corner, firstRow=True, firstColumn=True)
    assert _table_to_block(t).aligns == (("justify", "center"), ("right", ""))


def test_a_corner_needs_both_of_its_edges_switched_on():
    d = docx.Document()
    style = _table_style(d, "Corner Only", conditional={"nwCell": "both"})
    t = _filled_table(d, 2, 2, style, firstRow=True)
    assert _table_to_block(t).aligns[0][0] == ""


def test_row_banding_skips_the_header_row():
    d = docx.Document()
    style = _table_style(d, "Banded", conditional={
        "band1Horz": "center", "band2Horz": "right"})
    _set_style_band_sizes(style, row=1)
    t = _filled_table(d, 5, 1, style, firstRow=True, noVBand=True)
    assert _rows_col0(t) == ["", "center", "right", "center", "right"]


def test_band_size_groups_rows():
    d = docx.Document()
    style = _table_style(d, "Paired Bands", conditional={
        "band1Horz": "center", "band2Horz": "right"})
    _set_style_band_sizes(style, row=2)
    t = _filled_table(d, 4, 1, style, noVBand=True)
    assert _rows_col0(t) == ["center", "center", "right", "right"]


def test_without_a_band_size_word_does_not_band():
    """Word treats a missing band size as 0 -- no banding (ECMA-376 says 1)."""
    d = docx.Document()
    style = _table_style(d, "Unsized Bands", conditional={
        "band1Horz": "center", "band2Horz": "right"})
    t = _filled_table(d, 3, 1, style, noVBand=True)
    assert _rows_col0(t) == ["", "", ""]


def test_nohband_switches_row_banding_off():
    d = docx.Document()
    style = _table_style(d, "Banded", conditional={"band1Horz": "center"})
    _set_style_band_sizes(style, row=1)
    t = _filled_table(d, 3, 1, style, noHBand=True, noVBand=True)
    assert _rows_col0(t) == ["", "", ""]


def test_column_bands_beat_row_bands_and_the_total_row_is_not_banded():
    d = docx.Document()
    style = _table_style(d, "Criss Cross", conditional={
        "band1Horz": "center", "band1Vert": "right", "lastRow": "both"})
    _set_style_band_sizes(style, row=1, col=1)
    t = _filled_table(d, 3, 2, style, lastRow=True)
    assert _table_to_block(t).aligns == (
        ("right", "center"),        # band1 row; band1 column wins in col 0
        ("right", ""),              # band2 row sets nothing
        ("justify", "justify"),     # total row: no row band, row beats column
    )


def test_a_table_without_tbllook_gets_words_default_flags():
    """No `w:tblLook`: Word assumes 0x04A0 -- header row and first column
    on (ECMA-376 says all off)."""
    d = docx.Document()
    style = _table_style(d, "Edges", conditional={
        "firstRow": "center", "firstCol": "right"})
    t = _filled_table(d, 2, 2, style)
    for old in t._tbl.tblPr.findall(qn("w:tblLook")):
        t._tbl.tblPr.remove(old)
    assert _table_to_block(t).aligns == (("center", "center"), ("right", ""))


def test_named_tbllook_attributes_win_over_the_hex_value():
    d = docx.Document()
    style = _table_style(d, "Header Table", conditional={"firstRow": "center"})
    t = _filled_table(d, 2, 1, style, firstRow=False)
    t._tbl.tblPr.find(qn("w:tblLook")).set(qn("w:val"), "0020")
    assert _rows_col0(t) == ["", ""]


def _remove_override_setting(document) -> None:
    compat = document.settings.element.find(qn("w:compat"))
    if compat is None:
        return
    for setting in list(compat.findall(qn("w:compatSetting"))):
        if setting.get(qn("w:name")) == "overrideTableStyleFontSizeAndJustification":
            compat.remove(setting)


@pytest.mark.parametrize("override, expected", [(True, ""), (False, "center")])
def test_left_in_the_default_style_under_the_compatibility_setting(
    override, expected,
):
    """Without `overrideTableStyleFontSizeAndJustification`, a LEFT set by
    the default paragraph style does not override the table style; with it
    (Word 2013 and later, and python-docx's template), the paragraph style
    wins as usual."""
    d = docx.Document()
    d.styles["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if not override:
        _remove_override_setting(d)
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    assert _table_to_block(t).aligns == ((expected,),)


def test_the_compatibility_rule_covers_only_the_default_style_itself():
    d = docx.Document()
    _remove_override_setting(d)
    left = d.styles.add_style("Left Cell", WD_STYLE_TYPE.PARAGRAPH)
    left.base_style = d.styles["Normal"]
    left.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    t.cell(0, 0).paragraphs[0].style = left
    assert _table_to_block(t).aligns == (("",),)


def test_conditional_formats_merge_per_type_through_basedon():
    d = docx.Document()
    base = _table_style(d, "Base Table", conditional={
        "firstRow": "center", "lastRow": "right"})
    derived = _table_style(d, "Derived Table", based_on=base,
                           conditional={"firstRow": "both"})
    t = _filled_table(d, 3, 1, derived, firstRow=True, lastRow=True)
    assert _rows_col0(t) == ["justify", "", "right"]


def test_a_table_naming_a_missing_style_uses_the_default_table_style():
    d = docx.Document()
    defaults = [s for s in d.styles.element.findall(qn("w:style"))
                if s.get(qn("w:type")) == "table"
                and s.get(qn("w:default")) in ("1", "true", "on")]
    assert defaults, "python-docx's template always has a default table style"
    _append_jc(defaults[-1], "right")
    t = _filled_table(d, 1, 1)
    tbl_pr = t._tbl.tblPr
    for old in tbl_pr.findall(qn("w:tblStyle")):
        tbl_pr.remove(old)
    missing = OxmlElement("w:tblStyle")
    missing.set(qn("w:val"), "NoSuchTableStyle")
    tbl_pr.insert(0, missing)
    assert _table_to_block(t).aligns == (("right",),)


def test_each_table_style_is_resolved_once_per_document(monkeypatch):
    calls = []
    real = docx_parser._resolve_table_style
    monkeypatch.setattr(
        docx_parser, "_resolve_table_style",
        lambda styles, style_id: calls.append(style_id) or real(styles, style_id))
    d = docx.Document()
    style = _table_style(d, "Centred Table", base="center")
    for table in [_filled_table(d, 3, 3, style) for _ in range(4)]:
        _table_to_block(table)
    assert calls == [style.style_id]


def test_a_one_row_table_treats_its_only_row_as_the_header():
    d = docx.Document()
    style = _table_style(d, "Both Edges", conditional={
        "firstRow": "center", "lastRow": "right"})
    t = _filled_table(d, 1, 1, style, firstRow=True, lastRow=True)
    assert _table_to_block(t).aligns == (("center",),)


def test_a_paragraph_style_and_a_table_style_sharing_an_id_stay_apart():
    """A hand-edited file can give a paragraph style and a table style the
    same id. Each lookup has to find its own kind, or a table silently takes
    the paragraph style's alignment and loses its real header formatting."""
    d = docx.Document()
    para = d.styles.add_style("Dup Paragraph", WD_STYLE_TYPE.PARAGRAPH)
    para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    table_style = _table_style(d, "Dup Table", conditional={"firstRow": "center"})
    para.element.set(qn("w:styleId"), "Dup")
    table_style.element.set(qn("w:styleId"), "Dup")

    t = _filled_table(d, 2, 1, table_style, firstRow=True)
    p = d.add_paragraph("Right-aligned by the paragraph style.", style=para)
    assert t._tbl.tblPr.find(qn("w:tblStyle")).get(qn("w:val")) == "Dup"
    assert _table_to_block(t).aligns == (("center",), ("",))
    assert paragraph_alignment(p) == "right"


def test_a_duplicated_settings_relationship_does_not_crash_the_parse():
    """python-docx raises ValueError when a hand-edited file relates two
    settings parts. That must not reach the editor as a traceback."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    d = docx.Document()
    rels = d.part.rels
    (settings_rel,) = [r for r in rels.values() if r.reltype == RT.SETTINGS]
    rels.add_relationship(RT.SETTINGS, settings_rel.target_part,
                          "rIdDuplicateSettings")
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    assert _table_to_block(t).aligns == (("center",),)


def test_a_document_without_a_settings_part_gets_the_compatibility_rule():
    """No settings part means no opt-out, so Word's older rule applies: a
    LEFT in the default paragraph style yields to the table style."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    d = docx.Document()
    d.styles["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    rels = d.part.rels
    for r_id in [r_id for r_id, r in rels.items() if r.reltype == RT.SETTINGS]:
        rels.pop(r_id)
    t = _filled_table(d, 1, 1, _table_style(d, "Centred Table", base="center"))
    assert _table_to_block(t).aligns == (("center",),)


# ---------- rendering ----------
def _newsletter(*blocks) -> Newsletter:
    return Newsletter(
        masthead=Masthead("MERIDIAN", "", "", "VOL. 1 | ISSUE NO. 1 | MAY 2026"),
        sections=(Section(number=1, title="News", blocks=tuple(blocks)),),
    )


def _style_of(html: str, tag: str, text: str) -> str:
    """Whitespace-free inline style of the one `tag` whose text is `text`."""
    soup = BeautifulSoup(html, "html.parser")
    matches = [e for e in soup.find_all(tag) if e.get_text(strip=True) == text]
    assert len(matches) == 1, (
        f"expected one <{tag}> with text {text!r}, found {len(matches)} -- "
        "give each element in the test a distinct text")
    return re.sub(r"\s+", "", matches[0].get("style", ""))


@pytest.mark.parametrize("aligns, index, expected", [
    ("center", (), "center"),
    (("justify", "right"), (1,), "right"),
    ((("center",), ("", "right")), (1, 1), "right"),
    (("center",), (5,), ""),                  # shorter than the cells
    ((), (0, 0), ""),
    (None, (0,), ""),
    ((("center",),), (0,), ""),               # a row, not a value
    ((["center"],), (0,), ""),                # unhashable -- must not raise
    # The renderer re-checks the allowlist: a hand-built block's value
    # lands in a style attribute, where autoescaping does not stop a `;`.
    (("right;background:url(https://evil.example/x)",), (0,), ""),
    (("left",), (0,), ""),
])
def test_align_at_returns_only_allowlisted_values(aligns, index, expected):
    assert _align_at(aligns, *index) == expected


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
