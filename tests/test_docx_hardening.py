"""Regression tests for the crafted-DOCX security round.

Every test here reproduces something that was demonstrated against the
real code before the fix. The DOCX is attacker-influenceable in practice
-- a department contributor, a forwarded file, a compromised co-author
account -- and the resulting email is sent from the editor's own mailbox
to ~50 institutional recipients, so it inherits the newsletter's trust.
"""

from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import pytest

from scripts.config import MERIDIAN_TEMPLATE
from scripts.docx_parser import parse
from scripts.inliner import inline
from scripts.renderer import render
from scripts.text_utils import is_safe_url_scheme
from scripts.validator import validate

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
       'relationships"')


def _docx(tmp_path: Path, body_xml: str, rels_extra: str = "") -> Path:
    """A real DOCX with a hand-crafted body (and optionally extra rels)."""
    out = tmp_path / "crafted.docx"
    with zipfile.ZipFile(MERIDIAN_TEMPLATE) as zin, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(
                    item,
                    f'<?xml version="1.0"?><w:document {_NS}>'
                    f"<w:body>{body_xml}</w:body></w:document>")
            elif item.filename == "word/_rels/document.xml.rels" and rels_extra:
                base = zin.read(item.filename).decode()
                zout.writestr(item, base.replace(
                    "</Relationships>", rels_extra + "</Relationships>"))
            else:
                zout.writestr(item, zin.read(item.filename))
    return out


def _links_docx(tmp_path: Path, targets: list[str]) -> Path:
    rels = "".join(
        f'<Relationship Id="rH{i}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/hyperlink" Target="{t}" '
        f'TargetMode="External"/>'
        for i, t in enumerate(targets))
    body = "".join(
        f'<w:p><w:hyperlink r:id="rH{i}"><w:r><w:t>Faculty portal</w:t>'
        f"</w:r></w:hyperlink></w:p>"
        for i in range(len(targets)))
    return _docx(tmp_path, body, rels)


# ---------- URL schemes ------------------------------------------------

def test_hostile_url_schemes_never_reach_the_rendered_email(tmp_path):
    """The escape at the href only stopped an attribute breakout -- it
    said nothing about WHERE the link went. `file://host/share/x` is the
    sharp end: in Outlook on a domain-joined machine that is a UNC path,
    so one click authenticates the recipient to the attacker over SMB and
    leaks a NetNTLMv2 hash. The mail passes SPF/DKIM/DMARC because it
    came from the editor's own mailbox."""
    hostile = [
        "file://attacker.example.com/share/x",
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "JaVaScRiPt:alert(2)",          # case variation
        "ms-msdt:/id PCWDiagnostic",    # arbitrary protocol handler
    ]
    legit = ["https://legit.example.jp/news", "mailto:dean@example.ac.jp"]

    final = inline(render(parse(_links_docx(tmp_path, hostile + legit))))

    for probe in ("file://", "javascript", "data:text/html", "vbscript",
                  "ms-msdt", "attacker.example.com"):
        assert probe not in final, f"{probe!r} reached the recipient's email"
    assert "legit.example.jp" in final, "a legitimate https link was dropped"
    assert "dean@example.ac.jp" in final, "a legitimate mailto was dropped"


def test_the_editor_is_told_a_link_was_removed(tmp_path):
    """Silently losing a link the editor meant to include would be its
    own failure -- they must be able to tell the difference between
    'the toolkit protected me' and 'my link vanished'."""
    final = inline(render(parse(_links_docx(
        tmp_path, ["javascript:alert(1)", "https://ok.example.jp"]))))
    result = validate(final, check_remote=False)

    assert any("will not send to recipients" in w for w in result.warnings)
    assert result.ok, "a dropped link is a warning, not a hard block"


def test_the_rejected_url_is_not_echoed_into_the_message(tmp_path):
    """An early version of this fix put the rejected URL in a `data-`
    attribute so the validator could name it. That would have shipped
    the attacker's string into ~50 mailboxes as inert text, benefiting
    nobody -- the editor reads it on the console instead."""
    final = inline(render(parse(_links_docx(
        tmp_path, ["file://attacker.example.com/share/x"]))))

    assert "attacker.example.com" not in final
    assert "data-dropped-href" not in final


def test_the_validator_hard_blocks_an_unsafe_scheme_it_can_see():
    """It collected only `http(s)` hrefs, so a document carrying six
    hostile links reported "Links: 1 (0 broken)" and the manifest
    recorded the same count -- the audit trail actively asserted the
    message was clean. If one ever reaches the built HTML despite the
    renderer's guard, that is a toolkit bug and the send must stop."""
    html = ('<html><body>'
            '<a href="https://ok.example.jp">ok</a>'
            '<a href="file://evil.example/share">bad</a>'
            '<a href="javascript:alert(1)">bad2</a>'
            "</body></html>")
    result = validate(html, check_remote=False)

    assert not result.ok
    assert any("not safe to send" in e for e in result.errors)
    assert result.anchor_urls == ("https://ok.example.jp",)


@pytest.mark.parametrize("href", [
    # Written as an escape on purpose: a literal U+200B here would be
    # invisible to a reviewer, which is the exact property the test
    # is about.
    "java​script:alert(1)",     # zero-width space inside the scheme
    "\x01javascript:alert(1)",        # leading control character
    "  javascript:alert(1)",          # leading whitespace
    "ｊａｖａｓｃｒｉｐｔ:alert(1)",
    "#anchor", "/relative", "",
])
def test_scheme_check_resists_normalisation_bypasses(href):
    assert not is_safe_url_scheme(href)


@pytest.mark.parametrize("href", [
    "https://ok.example.jp", "HTTPS://OK.EXAMPLE.JP",
    "http://ok.example.jp", "mailto:dean@example.ac.jp",
])
def test_scheme_check_keeps_legitimate_links(href):
    assert is_safe_url_scheme(href)


# ---------- table geometry --------------------------------------------

def test_gridspan_cannot_burn_unbounded_cpu(tmp_path):
    """`_Row.cells` expands `w:gridSpan` eagerly and the value is an
    unbounded int from attacker XML. A 1.4 KB DOCX declaring 50,000,000
    cost minutes of CPU and hundreds of MB -- and it is reachable from
    `_extract_masthead`, which runs on EVERY document before any parsing
    decision. In the browser build it pins the only worker thread."""
    body = ('<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="5000000"/></w:tcPr>'
            "<w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>y</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    docx = _docx(tmp_path, body)

    start = time.monotonic()
    parse(docx)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"gridSpan expansion took {elapsed:.1f}s"


def test_vmerge_chain_does_not_recurse(tmp_path):
    """`_Row.cells` walks `_tc_above` recursively for every
    `w:vMerge="continue"` row -- quadratic, then `RecursionError`."""
    rows = ('<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr>'
            "<w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc></w:tr>")
    rows += ('<w:tr><w:tc><w:tcPr><w:vMerge w:val="continue"/></w:tcPr>'
             "<w:p/></w:tc></w:tr>") * 3000
    docx = _docx(tmp_path, f"<w:tbl>{rows}</w:tbl>")

    start = time.monotonic()
    parse(docx)          # must not raise RecursionError
    assert time.monotonic() - start < 10.0


# ---------- crashes that fire without an attacker ----------------------

def test_a_one_column_first_table_does_not_crash(tmp_path):
    """`_extract_masthead` indexed `rows[0].cells[1]` unconditionally.
    A single-column layout table on page 1 is ordinary in Word documents
    written outside the template -- and this runs BEFORE the strict /
    lenient decision, so it defeated the v1.1.2 lenient parse whose
    entire purpose is accepting arbitrary documents."""
    body = ("<w:tbl><w:tr><w:tc><w:p><w:r><w:t>only column</w:t></w:r>"
            "</w:p></w:tc></w:tr></w:tbl>"
            "<w:p><w:r><w:t>1. Research</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Body text.</w:t></w:r></w:p>")
    newsletter = parse(_docx(tmp_path, body))
    assert newsletter.sections


def test_a_zero_row_first_table_does_not_crash(tmp_path):
    newsletter = parse(_docx(
        tmp_path,
        "<w:tbl></w:tbl><w:p><w:r><w:t>1. Research</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Body.</w:t></w:r></w:p>"))
    assert newsletter.sections


def test_an_absurdly_long_section_number_does_not_crash(tmp_path):
    """CPython 3.11+ raises on `int()` of a >4300-digit string, so a
    paragraph of 5000 digits plus '. Boom' crashed the parse."""
    body = (f'<w:p><w:r><w:t>{"9" * 5000}. Boom</w:t></w:r></w:p>'
            "<w:p><w:r><w:t>Body.</w:t></w:r></w:p>")
    parse(_docx(tmp_path, body))   # must not raise


# ---------------------------------------------------------------------
# Round-19: findings from the PR review of the tracked-changes traversal
# ---------------------------------------------------------------------

def test_nested_tracked_changes_do_not_grow_the_call_stack():
    """`_iter_content_children` walks an explicit stack, not the C one.

    The review flagged this as a `RecursionError` of the same shape as
    the `w:vMerge` chain. It is not, and the difference is worth
    recording: libxml2 refuses documents nested beyond ~256 elements and
    python-docx does not pass `XML_PARSE_HUGE`, so a `w:ins` chain that
    arrives *through the parser* is bounded well inside Python's limit.
    `_tc_above` recursion, by contrast, scales with the number of
    sibling ROWS, which no nesting cap bounds at all -- which is why a
    ~3000-row chain really did raise `RecursionError`.

    So this pins the property, not a crash. The tree is built with the
    lxml API rather than parsed, because the parser cap is exactly the
    external default the rewrite exists not to depend on -- and because
    that cap turns out to differ by one between libxml2 builds, which a
    hardcoded depth discovered the hard way on the Linux and macOS
    runners.
    """
    from lxml import etree

    from scripts.docx_parser import _iter_content_children

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    depth = 5000  # far beyond anything the parser would admit

    root = etree.Element(f"{{{W}}}p", nsmap={"w": W})
    node = root
    for _ in range(depth):
        node = etree.SubElement(node, f"{{{W}}}ins")
    run = etree.SubElement(node, f"{{{W}}}r")
    etree.SubElement(run, f"{{{W}}}t").text = "payload"

    # A recursive implementation cannot pass this at any sane limit; an
    # iterative one does not notice the depth at all.
    limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(100)
        children = list(_iter_content_children(root))
    finally:
        sys.setrecursionlimit(limit)

    assert len(children) == 1
    assert children[0].tag == f"{{{W}}}r"


def test_deletions_stay_excluded_however_deeply_they_are_nested():
    """The traversal rewrite must not start publishing struck-out text.

    `w:del` content is the one thing here that would be actively harmful
    to emit: someone deleted a sentence, and printing it in a newsletter
    going to ~50 people is worse than dropping it.
    """
    from lxml import etree

    from scripts.docx_parser import _iter_content_children

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = etree.Element(f"{{{W}}}p", nsmap={"w": W})

    node = root
    for _ in range(50):
        node = etree.SubElement(node, f"{{{W}}}ins")
    kept = etree.SubElement(node, f"{{{W}}}r")

    # A deletion buried inside the same insertion chain, and a moveFrom
    # at the top level.
    dropped = etree.SubElement(node, f"{{{W}}}del")
    etree.SubElement(dropped, f"{{{W}}}r")
    moved_away = etree.SubElement(root, f"{{{W}}}moveFrom")
    etree.SubElement(moved_away, f"{{{W}}}r")

    children = list(_iter_content_children(root))
    assert children == [kept]


def test_total_cell_budget_is_actually_enforced():
    """`MAX_TABLE_ROWS` and `MAX_TABLE_COLS` bound each dimension
    separately, so on their own they admit 500 x 64 = 32,000 cells --
    more than the 20,000 total the module declares. The constant was
    defined and never read, which is worse than not declaring it: it
    reads as a guarantee nobody was providing.

    Cost is per cell, not per row or per column -- each one runs
    `paragraph_to_html` over its paragraphs.
    """
    from docx.oxml.parser import parse_xml
    from docx.table import Table

    from scripts.docx_parser import (
        MAX_TABLE_CELLS_TOTAL,
        MAX_TABLE_COLS,
        MAX_TABLE_ROWS,
        _table_to_block,
    )

    assert MAX_TABLE_ROWS * MAX_TABLE_COLS > MAX_TABLE_CELLS_TOTAL, (
        "this test is meaningless unless the per-dimension caps can "
        "exceed the total on their own")

    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    row = "<w:tr>" + "<w:tc><w:p><w:r><w:t>x</w:t></w:r></w:p></w:tc>" * 64 + "</w:tr>"
    tbl = parse_xml(f"<w:tbl {ns}>" + row * MAX_TABLE_ROWS + "</w:tbl>")

    block = _table_to_block(Table(tbl, None))
    total = sum(len(r) for r in block.rows)
    assert total <= MAX_TABLE_CELLS_TOTAL, (
        f"emitted {total} cells against a declared cap of "
        f"{MAX_TABLE_CELLS_TOTAL}")
