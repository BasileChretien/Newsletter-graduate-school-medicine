"""Raw OXML helpers for python-docx gaps (shading, borders, fields, etc.)."""

from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _qn(tag: str):
    return qn(tag)


def set_cell_shading(cell, hex_fill: str) -> None:
    """Apply a solid fill color to a table cell (no leading #)."""
    fill = hex_fill.lstrip("#").upper()
    tc_pr = cell._tc.get_or_add_tcPr()
    # Remove any existing shading element
    for shd in tc_pr.findall(_qn("w:shd")):
        tc_pr.remove(shd)
    shd = OxmlElement("w:shd")
    shd.set(_qn("w:val"), "clear")
    shd.set(_qn("w:color"), "auto")
    shd.set(_qn("w:fill"), fill)
    tc_pr.append(shd)


def set_cell_borders(cell, *, top=None, bottom=None, left=None, right=None,
                     inside_h=None, inside_v=None) -> None:
    """Apply borders to a single cell. Each border is dict(sz, val, color)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(_qn("w:tcBorders")):
        tc_pr.remove(old)
    borders_el = OxmlElement("w:tcBorders")
    sides = {
        "top": top, "bottom": bottom, "left": left, "right": right,
        "insideH": inside_h, "insideV": inside_v,
    }
    for name, spec in sides.items():
        if spec is None:
            continue
        b = OxmlElement(f"w:{name}")
        b.set(_qn("w:val"), spec.get("val", "single"))
        b.set(_qn("w:sz"), str(spec.get("sz", 4)))  # 1/8 pt units
        b.set(_qn("w:space"), str(spec.get("space", 0)))
        b.set(_qn("w:color"), spec.get("color", "000000").lstrip("#").upper())
        borders_el.append(b)
    tc_pr.append(borders_el)


def set_cell_margins(cell, *, top=80, bottom=80, left=100, right=100) -> None:
    """Cell margins in twentieths of a point (1pt = 20)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(_qn("w:tcMar")):
        tc_pr.remove(old)
    mar = OxmlElement("w:tcMar")
    for name, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        m = OxmlElement(f"w:{name}")
        m.set(_qn("w:w"), str(val))
        m.set(_qn("w:type"), "dxa")
        mar.append(m)
    tc_pr.append(mar)


def set_paragraph_border(paragraph, *, position="bottom", sz=6, color="C9A96E",
                         val="single", space=4) -> None:
    """Add a border to a paragraph (e.g. bottom border for a divider rule)."""
    p_pr = paragraph._p.get_or_add_pPr()
    for old in p_pr.findall(_qn("w:pBdr")):
        p_pr.remove(old)
    pbdr = OxmlElement("w:pBdr")
    side = OxmlElement(f"w:{position}")
    side.set(_qn("w:val"), val)
    side.set(_qn("w:sz"), str(sz))
    side.set(_qn("w:space"), str(space))
    side.set(_qn("w:color"), color.lstrip("#").upper())
    pbdr.append(side)
    p_pr.append(pbdr)


def set_run_letter_spacing(run, twentieths: int) -> None:
    """Add tracking (letter spacing) in twentieths of a point."""
    r_pr = run._r.get_or_add_rPr()
    for old in r_pr.findall(_qn("w:spacing")):
        r_pr.remove(old)
    sp = OxmlElement("w:spacing")
    sp.set(_qn("w:val"), str(twentieths))
    r_pr.append(sp)


def set_run_small_caps(run) -> None:
    r_pr = run._r.get_or_add_rPr()
    for old in r_pr.findall(_qn("w:smallCaps")):
        r_pr.remove(old)
    sc = OxmlElement("w:smallCaps")
    sc.set(_qn("w:val"), "1")
    r_pr.append(sc)


def set_run_all_caps(run) -> None:
    r_pr = run._r.get_or_add_rPr()
    for old in r_pr.findall(_qn("w:caps")):
        r_pr.remove(old)
    el = OxmlElement("w:caps")
    el.set(_qn("w:val"), "1")
    r_pr.append(el)


def add_page_field(paragraph, instr: str = "PAGE") -> None:
    """Insert a field code (PAGE / NUMPAGES / DATE) into a paragraph."""
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(_qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText")
    instr_el.set(_qn("xml:space"), "preserve")
    instr_el.text = f" {instr} "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(_qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(_qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr_el)
    run._r.append(fld_sep)
    run._r.append(fld_end)


def set_table_fixed_layout(table) -> None:
    """Switch a table to fixed-width layout so column widths are honored."""
    tbl_pr = table._tbl.tblPr
    for old in tbl_pr.findall(_qn("w:tblLayout")):
        tbl_pr.remove(old)
    layout = OxmlElement("w:tblLayout")
    layout.set(_qn("w:type"), "fixed")
    tbl_pr.append(layout)


def remove_table_borders(table) -> None:
    """Strip all borders from a table (used for layout tables)."""
    tbl_pr = table._tbl.tblPr
    for old in tbl_pr.findall(_qn("w:tblBorders")):
        tbl_pr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(_qn("w:val"), "nil")
        borders.append(b)
    tbl_pr.append(borders)


def set_row_height(row, twentieths: int, *, exact: bool = False) -> None:
    """Set row height (exact or at-least), in twentieths of a point."""
    tr_pr = row._tr.get_or_add_trPr()
    for old in tr_pr.findall(_qn("w:trHeight")):
        tr_pr.remove(old)
    h = OxmlElement("w:trHeight")
    h.set(_qn("w:val"), str(twentieths))
    h.set(_qn("w:hRule"), "exact" if exact else "atLeast")
    tr_pr.append(h)
