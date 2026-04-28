"""Tests for editor-defined sections.

The toolkit supports any number of sections, any titles, any
sub-headings -- as long as the editor uses Word's heading styles or
keeps the "01 -- TITLE" / "1. Title" numbered-heading pattern. These
tests cover the flexibility the rebrand introduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Need a python-docx Document writer for the synthetic-DOCX scenarios.
docx = pytest.importorskip("docx")


def _make_doc(tmp_path: Path, paragraphs: list[tuple[str, str | None]]) -> Path:
    """Build a minimal one-table-masthead DOCX from a list of
    (text, style_name) tuples. style_name=None -> Normal paragraph."""
    doc = docx.Document()
    # Masthead table (the parser skips table_index == 1).
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[1].text = "MERIDIAN\nTagline\nSubtitle\nVOL. X"
    for text, style in paragraphs:
        p = doc.add_paragraph(text)
        if style is not None:
            try:
                p.style = doc.styles[style]
            except KeyError:
                pass
    out = tmp_path / "synthetic.docx"
    doc.save(str(out))
    return out


def test_three_sections_with_arbitrary_titles(tmp_path):
    """Editor adds three custom sections; toolkit accepts all three."""
    from scripts.docx_parser import parse

    doc_path = _make_doc(tmp_path, [
        ("1.  Hospital News", None),
        ("Some hospital body text.", None),
        ("2.  Awards & Honours", None),
        ("Some awards body text.", None),
        ("3.  Save the Date", None),
        ("Some events body text.", None),
    ])
    nl = parse(doc_path)
    assert len(nl.sections) == 3
    assert nl.sections[0].title == "Hospital News"
    assert nl.sections[1].title == "Awards & Honours"
    assert nl.sections[2].title == "Save the Date"


def test_subheading_via_word_heading_style(tmp_path):
    """Word's built-in 'Heading 2' style is recognised as a sub-heading."""
    from scripts.docx_parser import Heading, parse

    doc_path = _make_doc(tmp_path, [
        ("1.  Free Section", None),
        ("Sub-heading via Word style", "Heading 2"),
        ("Body paragraph below the sub-heading.", None),
    ])
    nl = parse(doc_path)
    assert len(nl.sections) == 1
    headings = [b.text for b in nl.sections[0].blocks
                if isinstance(b, Heading)]
    assert "Sub-heading via Word style" in headings


def test_subheading_via_bold_short_paragraph(tmp_path):
    """Heuristic: short bold paragraph without sentence punctuation."""
    from scripts.docx_parser import Heading, parse

    doc = docx.Document()
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[1].text = "MERIDIAN\nTagline\nSubtitle\nVOL. X"
    doc.add_paragraph("1.  Free Section")
    p = doc.add_paragraph()
    run = p.add_run("Bold Subhead")
    run.bold = True
    doc.add_paragraph("Body paragraph below.")
    out = tmp_path / "syn.docx"
    doc.save(str(out))

    from scripts.docx_parser import parse
    nl = parse(out)
    headings = [b.text for b in nl.sections[0].blocks
                if isinstance(b, Heading)]
    assert "Bold Subhead" in headings


def test_long_bold_paragraph_is_NOT_a_subhead(tmp_path):
    """A long bold paragraph (e.g. an emphasised body sentence) is body, not heading."""
    from scripts.docx_parser import BodyParagraph, Heading, parse

    doc = docx.Document()
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[1].text = "MERIDIAN\nTagline\nSubtitle\nVOL. X"
    doc.add_paragraph("1.  Section")
    p = doc.add_paragraph()
    long_text = (
        "This sentence is bold for emphasis but it is much longer than "
        "any reasonable sub-heading and ends with a period."
    )
    run = p.add_run(long_text)
    run.bold = True
    out = tmp_path / "syn.docx"
    doc.save(str(out))

    from scripts.docx_parser import parse
    nl = parse(out)
    headings = [b.text for b in nl.sections[0].blocks
                if isinstance(b, Heading)]
    assert long_text not in headings
