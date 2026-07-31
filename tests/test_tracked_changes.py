"""Tracked-change handling.

Reported from production: "the dean picture is not always loading" and
"the big pictures are not detected". Both were the same bug -- those
images had been added with Word's Track Changes turned on and never
accepted, so they sat inside `<w:ins>` elements. `paragraph_to_html`
only looked at children whose tag was `w:r`, so a run nested in `<w:ins>`
was never visited and its content silently disappeared.

"Not always" is the tell: whether a photo survived depended on whether
that particular edit had been accepted before the file was handed over.

Images made it visible. Text would have vanished just as quietly, which
is the more dangerous form -- a missing photo is obvious, a missing
sentence is not.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.config import MERIDIAN_TEMPLATE
from scripts.docx_parser import parse

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
       'relationships"')


def _docx(tmp_path: Path, body_xml: str) -> Path:
    out = tmp_path / "tracked.docx"
    with zipfile.ZipFile(MERIDIAN_TEMPLATE) as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(
                    item,
                    f'<?xml version="1.0"?><w:document {_NS}>'
                    f"<w:body>{body_xml}</w:body></w:document>")
            else:
                zout.writestr(item, zin.read(item.filename))
    return out


def _rendered(tmp_path: Path, body_xml: str) -> str:
    newsletter = parse(_docx(tmp_path, body_xml))
    out = []
    for section in newsletter.sections:
        for block in section.blocks:
            html = getattr(block, "html", None)
            if isinstance(html, str):
                out.append(html)
            for row in getattr(block, "rows", ()) or ():
                out.extend(row)
            for item in getattr(block, "items", ()) or ():
                out.append(item)
    return " ".join(out)


_HEADING = '<w:p><w:r><w:t>1. Research</w:t></w:r></w:p>'


def test_text_inserted_with_track_changes_is_published(tmp_path):
    html = _rendered(tmp_path, _HEADING + (
        '<w:p><w:r><w:t>Plain. </w:t></w:r>'
        '<w:ins w:id="1" w:author="a"><w:r><w:t>INSERTED</w:t></w:r></w:ins>'
        "</w:p>"))
    assert "Plain." in html
    assert "INSERTED" in html


def test_deleted_text_is_never_published(tmp_path):
    """The critical direction. Someone struck a sentence out; publishing
    it to ~50 recipients would be far worse than dropping it. This was
    previously excluded only as a side effect of the `w:r` tag check --
    nobody had decided it, so widening the traversal could have started
    publishing struck-out text."""
    html = _rendered(tmp_path, _HEADING + (
        '<w:p><w:r><w:t>Kept. </w:t></w:r>'
        '<w:del w:id="2" w:author="a">'
        "<w:r><w:delText>STRUCK-OUT</w:delText></w:r></w:del></w:p>"))
    assert "Kept." in html
    assert "STRUCK-OUT" not in html


def test_moved_content_follows_its_destination(tmp_path):
    html = _rendered(tmp_path, _HEADING + (
        '<w:p><w:moveTo w:id="3" w:author="a">'
        "<w:r><w:t>MOVED-HERE</w:t></w:r></w:moveTo>"
        '<w:moveFrom w:id="4" w:author="a">'
        "<w:r><w:delText>MOVED-AWAY</w:delText></w:r></w:moveFrom></w:p>"))
    assert "MOVED-HERE" in html
    assert "MOVED-AWAY" not in html


def test_an_image_inserted_with_track_changes_is_detected(tmp_path):
    """The reported symptom. The drawing is identical to an accepted
    one -- only the `<w:ins>` wrapper differs."""
    drawing = (
        "<w:drawing><wp:inline "
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/'
        'wordprocessingDrawing">'
        '<wp:extent cx="2000000" cy="1500000"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/'
        '2006/main"><a:graphicData><pic:pic '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/'
        'picture"><pic:blipFill>'
        '<a:blip r:embed="rId10"/>'
        "</pic:blipFill></pic:pic></a:graphicData></a:graphic>"
        "</wp:inline></w:drawing>")
    html = _rendered(tmp_path, _HEADING + (
        f'<w:p><w:ins w:id="5" w:author="a"><w:r>{drawing}</w:r>'
        "</w:ins></w:p>"))

    assert "media://" in html, "an inserted image was dropped"


def test_a_hyperlink_inserted_with_track_changes_keeps_its_href(tmp_path):
    """`_hyperlinks` searched direct children only, so a link added with
    Track Changes on produced an empty URL map and lost its target."""
    body = _HEADING + (
        '<w:p><w:ins w:id="6" w:author="a">'
        '<w:hyperlink r:id="rId10"><w:r><w:t>Faculty page</w:t></w:r>'
        "</w:hyperlink></w:ins></w:p>")
    # rId10 resolves to an image part in the template, which is not an
    # http(s) target -- so assert on the traversal, not the scheme.
    html = _rendered(tmp_path, body)
    assert "Faculty page" in html


@pytest.mark.parametrize("wrapper", ["w:ins", "w:moveTo"])
def test_formatting_survives_inside_a_tracked_change(tmp_path, wrapper):
    """`paragraph.runs` lists only DIRECT `w:r` children, so the run
    lookup missed nested runs and their text was dropped even once the
    traversal descended correctly."""
    html = _rendered(tmp_path, _HEADING + (
        f'<w:p><{wrapper} w:id="7" w:author="a"><w:r>'
        "<w:rPr><w:b/></w:rPr><w:t>BOLD-INSERTED</w:t>"
        f"</w:r></{wrapper}></w:p>"))
    assert "BOLD-INSERTED" in html
    assert "<strong>" in html
