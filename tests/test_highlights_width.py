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


def test_highlights_card_partial_uses_264px():
    """The partial template must hardcode width="264" / 264px so the
    inline attribute wins after css_inline, matching the CSS rule."""
    src = PARTIAL.read_text(encoding="utf-8")
    # No `width="272"` in the partial; we want exactly 264.
    assert 'width="272"' not in src, (
        "round-9 Visual H1: width=272 is the pre-bundle-26 value that "
        "overflows the 544px usable section width."
    )
    assert 'width:272px' not in src
    # Positive assertion: the highlights cards carry width="264".
    matches = re.findall(r'class="card"[^>]*width="(\d+)"', src)
    assert matches, (
        "expected at least one highlights `card` cell with a width attr "
        "in _block.html.j2"
    )
    for w in matches:
        assert int(w) == 264, (
            f"highlights card width={w}px in partial; must be 264 to fit "
            "two cards + 16px gutter inside 544px usable section width."
        )


def test_highlights_card_styles_match_partial():
    """The CSS rule must agree with the partial -- if a future
    refactor changes one without the other, this catches the drift."""
    css = STYLES.read_text(encoding="utf-8")
    src = PARTIAL.read_text(encoding="utf-8")
    css_match = re.search(
        r"table\.highlights td\.card\s*\{[^}]*width:\s*(\d+)px",
        css, flags=re.DOTALL,
    )
    assert css_match, "CSS rule for highlights card width missing"
    css_width = int(css_match.group(1))

    partial_widths = {
        int(w) for w in re.findall(r'class="card"[^>]*width="(\d+)"', src)
    }
    assert css_width in partial_widths, (
        f"CSS says width:{css_width}px but partial has widths "
        f"{partial_widths}. Update both."
    )


def test_two_cards_plus_gutter_fits_in_usable_section_width():
    """Sanity check on the math: 2 × card + 16px gutter must fit
    inside 600 - 28 - 28 = 544px usable section width."""
    css = STYLES.read_text(encoding="utf-8")
    css_match = re.search(
        r"table\.highlights td\.card\s*\{[^}]*width:\s*(\d+)px",
        css, flags=re.DOTALL,
    )
    assert css_match
    card_w = int(css_match.group(1))
    total = 2 * card_w + 16
    assert total <= 544, (
        f"2 × {card_w}px card + 16px gutter = {total}px, exceeds "
        "544px usable section width -> Outlook horizontal scroll."
    )
