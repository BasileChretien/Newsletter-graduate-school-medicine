"""Regression tests for the Featured Highlights card width.

Round-9 Visual H1: bundle 26 changed `.highlights td.card { width: 264px }`
in styles.css to fit two cards + 16px gutter inside the 600px container's
544px usable width. But it missed `_block.html.j2` which still hardcoded
`width="272"` -- inline style wins after css_inline, so the rendered cards
were 272px each (560px total, overflowing).

These tests pin the fix so a future template tweak can't silently
regress to the wider value.
"""

from __future__ import annotations

import re
from pathlib import Path

PARTIAL = (
    Path(__file__).parent.parent
    / "templates" / "partials" / "_block.html.j2"
)
STYLES = Path(__file__).parent.parent / "templates" / "styles.css"


# ---------- Bundle 29: content-box math correction ---------------------

# Visual / horizontal-padding values that drive the content-box math.
# Pinned here so a future tweak (e.g. denser cards, wider gutter)
# can be made by changing constants instead of recomputing by hand.
SECTION_USABLE_WIDTH_PX = 544   # 600 (container) - 28 - 28 (section padding)
HIGHLIGHTS_GUTTER_PX = 16
HIGHLIGHTS_CARD_H_PADDING_PX = 14   # 14 + 14 -- per styles.css `td.card`


def _read_card_content_width_from_css() -> int:
    css = STYLES.read_text(encoding="utf-8")
    css_match = re.search(
        r"table\.highlights td\.card\s*\{[^}]*width:\s*(\d+)px",
        css, flags=re.DOTALL,
    )
    assert css_match, "CSS rule for highlights card width missing"
    return int(css_match.group(1))


def _read_card_widths_from_partial() -> list[int]:
    """Robust to attribute reordering -- parse the HTML, don't regex
    expecting `class` before `width` (round-10 code-review LOW)."""
    from bs4 import BeautifulSoup
    src = PARTIAL.read_text(encoding="utf-8")
    soup = BeautifulSoup(src, "html.parser")
    out: list[int] = []
    for td in soup.find_all("td", class_="card"):
        w = td.get("width")
        if w is not None:
            out.append(int(w))
    return out


def test_highlights_card_partial_matches_css():
    """Round-10 Visual H1 follow-up: the partial template's
    `width="N"` attribute must match the CSS `width: Npx` rule. After
    bundle 29 they're both 236 (the content width that, with 14+14
    padding, renders to 264 px outer in Outlook's content-box mode)."""
    css_width = _read_card_content_width_from_css()
    partial_widths = _read_card_widths_from_partial()
    assert partial_widths, (
        "expected at least one highlights `card` cell with width attr "
        "in _block.html.j2"
    )
    for w in partial_widths:
        assert w == css_width, (
            f"highlights card width={w}px in partial != {css_width}px "
            "in CSS. Bundle 28's regression was exactly this kind of "
            "drift -- update both."
        )


def test_highlights_card_partial_does_not_use_pre_bundle_29_widths():
    """Guard against a regression to either the bundle-25/26 (272)
    or bundle-28 (264 outer-as-content) values."""
    partial_widths = _read_card_widths_from_partial()
    for w in partial_widths:
        assert w != 272, "width=272 is the pre-bundle-26 value (overflows)"
        assert w != 264, (
            "width=264 looks like the bundle-28 'outer width as content' "
            "mistake. With 14+14 padding the rendered outer is 292 -> "
            "overflow. Use 236 (content) so outer == 264."
        )


def test_two_cards_plus_padding_plus_gutter_fits_in_usable_section_width():
    """Round-10 Visual H1 + Email M3: with content-box rendering
    (Outlook 2016/2019 default), a card's RENDERED outer width is
    `content_width + 2 * h_padding`. The bundle-28 mistake was using
    264 as content (rendering 292) instead of as outer (rendering 264).

    Math: 2 * (content + 28) + 16 gutter <= 544 (usable).
       => content <= (544 - 16 - 56) / 2 = 236.
    """
    content = _read_card_content_width_from_css()
    rendered_outer = content + 2 * HIGHLIGHTS_CARD_H_PADDING_PX
    total = 2 * rendered_outer + HIGHLIGHTS_GUTTER_PX
    assert total <= SECTION_USABLE_WIDTH_PX, (
        f"2 × {rendered_outer}px (= {content}+{2*HIGHLIGHTS_CARD_H_PADDING_PX} "
        f"content+padding) + {HIGHLIGHTS_GUTTER_PX}px gutter = {total}px, "
        f"exceeds {SECTION_USABLE_WIDTH_PX}px usable section width -> "
        "Outlook horizontal scroll. Bundle 28 made this mistake by "
        "treating the 264 figure as content instead of outer."
    )


def test_highlights_gutter_uses_zwsp_and_mso_line_height():
    """Round-10 Visual M2: bundle 28 swapped the divider's spacer
    cells from `&nbsp;` to `&#8203;` (zero-width-space) plus
    `mso-line-height-rule:exactly`. The highlights gutter cell sat
    on the OLD `&nbsp;` rendering until bundle 29; in Outlook
    2016/2019 that produced occasional 1-2px height bumps in the
    gutter row. Pin the new contract."""
    src = PARTIAL.read_text(encoding="utf-8")
    # Find the gutter cell.
    gutter_match = re.search(
        r"<td[^>]*class=\"gutter\"[^>]*>(.*?)</td>",
        src, flags=re.DOTALL,
    )
    assert gutter_match, "highlights gutter cell missing in partial"
    gutter_block = gutter_match.group(0)
    assert "&#8203;" in gutter_block, (
        "highlights gutter must use &#8203; (zero-width-space), not "
        "&nbsp;, so Outlook 2016/2019 doesn't bump gutter height."
    )
    assert "&nbsp;" not in gutter_block, (
        "&nbsp; in the gutter is the bundle-28 mistake -- regressed."
    )
    assert "mso-line-height-rule" in gutter_block, (
        "highlights gutter cell must carry `mso-line-height-rule:exactly` "
        "so Outlook honors line-height:0."
    )


def test_highlights_card_padding_is_14px_per_side():
    """Math depends on the horizontal padding being 14 per side. Pin
    the value -- a future style edit that bumps padding without
    bumping content-width would silently overflow again."""
    css = STYLES.read_text(encoding="utf-8")
    pad_match = re.search(
        r"table\.highlights td\.card\s*\{[^}]*padding:\s*"
        r"\d+px\s+(\d+)px\s+\d+px\s+(\d+)px",
        css, flags=re.DOTALL,
    )
    assert pad_match, (
        "CSS .highlights td.card padding shorthand changed shape; "
        "fix the math test in test_highlights_width.py."
    )
    h_pad_right = int(pad_match.group(1))
    h_pad_left = int(pad_match.group(2))
    assert h_pad_right == HIGHLIGHTS_CARD_H_PADDING_PX
    assert h_pad_left == HIGHLIGHTS_CARD_H_PADDING_PX
