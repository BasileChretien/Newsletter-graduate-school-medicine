"""Regression tests for the masthead seal frame and other visual fixes.

Bundle 25 introduced a wrapping-table hairline frame around the seal
so Outlook desktop wouldn't render the white padding with the
parent's #EEF2F7 bg (a halo effect). Bundle 26 fixed two regressions
in that change:

* `font-size:0;line-height:0` on the wrapping td hid the alt-text
  fallback when Outlook desktop blocked images by default.
* The wrapping table had no `width` attribute; MSO renderer would
  balloon child tables, exposing the hairline as a vertical bar.

Bundle 27 added Outlook-safe divider (3-cell layout) and pinned
the subhead typography contract.

Pin all the above here so a future template edit can't silently
regress them.
"""

from __future__ import annotations

from pathlib import Path

from scripts.docx_parser import Masthead, Newsletter
from scripts.inliner import inline
from scripts.renderer import render


def _render_with_masthead() -> str:
    """Render a minimal newsletter with a masthead and run css_inline."""
    nl = Newsletter(
        masthead=Masthead(
            title="MERIDIAN",
            tagline="Where medicine meets the world.",
            subtitle="Newsletter",
            issue_line="VOL. 12 | ISSUE NO. 3 | MARCH 2026",
        ),
        sections=(),
    )
    return inline(render(nl))


def test_masthead_logo_does_not_set_font_size_zero_on_wrapping_td():
    """`font-size:0` / `line-height:0` on the wrapping td would
    collapse the alt-text fallback when Outlook blocks images.

    Regression guard for round-8 email-deliverability H1."""
    html = _render_with_masthead()
    masthead_block_start = html.find("masthead-logo")
    assert masthead_block_start != -1, "masthead-logo class missing"
    # Look at the next ~800 characters of HTML following the class
    # (covers the wrapping table + the img tag).
    block = html[masthead_block_start:masthead_block_start + 1200]
    assert "font-size:0" not in block, (
        "Wrapping td must NOT set font-size:0 -- it collapses the "
        "alt-text fallback in Outlook blocked-image mode."
    )
    assert "line-height:0" not in block, (
        "Wrapping td must NOT set line-height:0 -- same reason."
    )


def test_masthead_logo_wrapping_table_has_explicit_width():
    """The wrapping <table> must declare an explicit `width="80"`
    so MSO doesn't balloon it past the seal -- a child table
    without an explicit width can stretch and turn the hairline
    into a visible vertical bar.

    Regression guard for round-8 visual H1."""
    html = _render_with_masthead()
    block_start = html.find("masthead-logo")
    block = html[block_start:block_start + 1200]
    # The wrapping <table> must carry width="80" or width:80px.
    assert ('width="80"' in block) or ("width:80px" in block.replace(" ", "")), (
        "Wrapping <table> in masthead-logo missing explicit width=80; "
        f"block: {block!r}"
    )


def test_masthead_logo_keeps_hairline_border_after_inlining():
    """The 1px #C9D2DE hairline must survive the css_inline pass --
    it's the institutional frame. If a future inline `border:0` is
    added to the <img> or wrapping td, it would override the css.

    Regression guard for round-7 visual HIGH-1 (revisited bundle 25)."""
    html = _render_with_masthead()
    block_start = html.find("masthead-logo")
    block = html[block_start:block_start + 1200]
    assert "#C9D2DE" in block, (
        "Hairline #C9D2DE missing from masthead-logo block; "
        "wrapping td should carry `border:1px solid #C9D2DE`."
    )


def test_masthead_logo_preserves_alt_text():
    """Alt-text fallback must be present and readable in the rendered
    HTML so Outlook recipients with images blocked see the institution
    name instead of an empty box."""
    html = _render_with_masthead()
    block_start = html.find("masthead-logo")
    block = html[block_start:block_start + 1200]
    assert 'alt="Nagoya University Graduate School of Medicine"' in block, (
        "Masthead seal alt-text missing or modified -- recipients with "
        "images blocked would see no institution name."
    )


def test_masthead_logo_uses_white_background():
    """Frame is white (not the cream #EEF2F7 of the masthead) so the
    seal sits on a clean institutional ground."""
    html = _render_with_masthead()
    block_start = html.find("masthead-logo")
    block = html[block_start:block_start + 1200]
    assert "#FFFFFF" in block.upper() or 'bgcolor="#FFFFFF"' in block, (
        "Masthead seal frame must be white; got: {!r}".format(block[:300])
    )


# ---------- Bundle 27 visual fixes --------------------------------------

def test_divider_uses_outlook_safe_three_cell_layout():
    """Outlook desktop ignores `margin` on a <td>, which used to make
    the gold rule extend full-width. Round 8 Visual L1 wraps the
    divider in a 3-cell layout (spacer + rule + spacer).

    Round-9 code-review MEDIUM: don't ±-string-grep for `width="28"`
    near `class="divider"`; assert the *structural* invariant that the
    divider's parent <tr> has exactly 3 <td> children. The pixel
    width is a tuning value that can change without breaking
    Outlook-safety."""
    from bs4 import BeautifulSoup
    from scripts.docx_parser import Newsletter, Section

    nl = Newsletter(
        masthead=Masthead("MERIDIAN", "tag", "sub", "VOL. 1"),
        sections=(
            Section(number=1, title="A", blocks=()),
            Section(number=2, title="B", blocks=()),
        ),
    )
    html = inline(render(nl))

    soup = BeautifulSoup(html, "html.parser")
    dividers = soup.find_all(class_="divider")
    assert len(dividers) == 1, (
        f"Expected exactly one divider between two sections; "
        f"got {len(dividers)}."
    )
    divider_td = dividers[0]
    parent_tr = divider_td.find_parent("tr")
    assert parent_tr is not None
    sibling_tds = parent_tr.find_all("td", recursive=False)
    assert len(sibling_tds) == 3, (
        f"Divider <tr> must contain exactly 3 <td> children "
        f"(spacer + rule + spacer); got {len(sibling_tds)}."
    )
    # The middle cell IS the divider; the two outer cells are spacers.
    assert sibling_tds[1] is divider_td or "divider" in (
        sibling_tds[1].get("class") or [])


def test_divider_is_outlook_height_clamped():
    """Round-9 Email M2: Outlook desktop expands empty cells to
    font-line-height. Force exactly 1px via `mso-line-height-rule:exactly`
    on the spacer cells AND the rule cell so the divider doesn't
    silently become 15-18px tall in Outlook 2016/2019."""
    from bs4 import BeautifulSoup
    from scripts.docx_parser import Newsletter, Section

    nl = Newsletter(
        masthead=Masthead("MERIDIAN", "tag", "sub", "VOL. 1"),
        sections=(
            Section(number=1, title="A", blocks=()),
            Section(number=2, title="B", blocks=()),
        ),
    )
    html = inline(render(nl))
    soup = BeautifulSoup(html, "html.parser")
    parent_tr = soup.find(class_="divider").find_parent("tr")
    for td in parent_tr.find_all("td", recursive=False):
        style = (td.get("style") or "")
        assert "mso-line-height-rule" in style, (
            "Every <td> in the divider row must carry "
            "`mso-line-height-rule:exactly` so Outlook doesn't expand "
            "empty cells to font-line-height."
        )


def test_print_stylesheet_strips_masthead_background():
    """`@media print` must override the cream masthead bg + 8px blue
    rule so editors don't waste ink on the band when printing.

    Regression guard for round-8 Visual L3."""
    from scripts.inliner import _KEPT_STYLES
    assert ".masthead" in _KEPT_STYLES, (
        "_KEPT_STYLES must carry a print-mode override for .masthead"
    )
    no_spaces = _KEPT_STYLES.replace(" ", "")
    assert "background:#FFFFFF" in no_spaces


def test_print_stylesheet_strips_gold_rules():
    """Round-9 Visual M1: print mode must also strip the masthead's
    gold border-bottom AND the tagline's gold underline. Otherwise
    paper output shows four stacked horizontal lines around the
    title (1pt blue rule, two gold lines, the title between them)."""
    from scripts.inliner import _KEPT_STYLES
    no_spaces = _KEPT_STYLES.replace(" ", "")
    # masthead.border-bottom override
    assert "border-bottom:none!important" in no_spaces, (
        "@media print must override .masthead border-bottom (the gold "
        "rule under the issue-line)."
    )
    # Tagline border override appears separately.
    assert ".tagline" in _KEPT_STYLES, (
        "@media print must also override .masthead .tagline border-bottom "
        "(the gold underline beneath the tagline)."
    )


def test_subhead_uses_smaller_distinct_typography():
    """Round 8 Visual M4 + round 9 Visual H2: subhead is 12px NU
    blue (was 13px charcoal pre-bundle-27, then briefly 12px blue
    UPPERCASE which collided typographically with the 16px blue
    UPPERCASE section heading -- both serif, both bold, both blue).
    Bundle 28 keeps the smaller size + blue colour but DROPS the
    uppercase + letter-spacing so the subhead clearly reads as a
    child tier of the section heading."""
    css_path = Path(__file__).parent.parent / "templates" / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    subhead_idx = css.find(".subhead")
    assert subhead_idx >= 0
    subhead_block = css[subhead_idx:subhead_idx + 800]
    assert "font-size: 12px" in subhead_block, (
        ".subhead font-size must be 12px (was 13px before bundle 27)."
    )
    assert "color: #003F88" in subhead_block, (
        ".subhead must be NU blue so it ties visually to the section's "
        "left bar."
    )
    # Bundle 28 differentiation guard: uppercase + letter-spacing must
    # NOT both reappear -- that's the section-heading's signature.
    assert "text-transform: uppercase" not in subhead_block, (
        ".subhead must NOT be uppercase -- collides with section-heading "
        "typographic rank (round-9 Visual H2)."
    )
