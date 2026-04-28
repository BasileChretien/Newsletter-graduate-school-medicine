"""Run / paragraph / color primitives shared by every restyler.

Extracted from `build_template.py` in bundle 27 so the orchestration
in `_elements.py` reads as a flat list of high-level steps rather
than scrolling past 70 lines of color-helper boilerplate.

Public surface (re-exported by the package `__init__`):

* `rgb(hex_str)`           -- "#003F88" -> RGBColor
* `PRIMARY` / `ACCENT` / `TEXT` / `MUTED`  -- palette as RGBColor
* `style_run(run, ...)`    -- one-liner run styling
* `style_paragraph(p, ...)` -- one-liner paragraph styling
* `_normalize_body_run(run)` -- default body styling + legacy-palette sweep
"""

from __future__ import annotations

from docx.enum.text import WD_LINE_SPACING
from docx.shared import Inches, Pt, RGBColor

from scripts.config import PALETTE
from scripts.oxml_helpers import set_run_letter_spacing, set_run_small_caps


# ---------- color helpers ----------
def rgb(hex_str: str) -> RGBColor:
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


PRIMARY = rgb(PALETTE["primary"])
ACCENT = rgb(PALETTE["accent"])
TEXT = rgb(PALETTE["text"])
MUTED = rgb(PALETTE["muted"])

# Module-level constants for the legacy palette colors swept by
# `_normalize_body_run`. Hoisted out of the inner loop -- previously
# allocated 3 RGBColor objects per run on every restyle pass.
_LEGACY_BLUE = RGBColor(0x2D, 0x2D, 0x8E)
_LEGACY_MUSTARD = RGBColor(0xC8, 0xA4, 0x15)
_LEGACY_PASTEL = RGBColor(0xAA, 0xBB, 0xCC)


def _normalize_body_run(run) -> None:
    """Apply default body styling (Calibri / charcoal / 10.5pt) to a run.

    Also clears the original Nagoya template's blanket-italic placeholder
    formatting (e.g. "[Author(s)]", `doi:[DOI]`) -- once the editor types
    real content, persistent italic reads as "this whole list is a
    footnote". The HTML pipeline does the same via `_strip_em` in the
    renderer; this is the DOCX-side counterpart so both outputs ship
    consistently.

    Stale-palette sweep: the original Nagoya template carried hard-coded
    `#2D2D8E` (old indigo), `#C8A415` (mustard), and `#AABBCC` (placeholder
    pastel) on certain runs. After the NU blue rebrand those clash with
    `#003F88`; we promote them to the new palette here.
    """
    if run.font.name in (None, "", "Arial"):
        run.font.name = "Calibri"
    if run.font.size is None:
        run.font.size = Pt(10.5)

    # Replace stale legacy palette colors with the NU blue palette.
    # Without this sweep, runs the editor never touched ship with
    # template-leftover indigo/mustard/pastel.
    cur = run.font.color.rgb
    if cur is None:
        run.font.color.rgb = TEXT
    elif cur == _LEGACY_BLUE:
        run.font.color.rgb = PRIMARY
    elif cur == _LEGACY_MUSTARD:
        run.font.color.rgb = ACCENT
    elif cur == _LEGACY_PASTEL:
        run.font.color.rgb = TEXT

    # Clear the template's default italics on placeholder text. Editors
    # who genuinely need italic (a journal title, a pull quote) can
    # re-enable it locally in Word.
    if run.italic:
        run.italic = False


# ---------- run/paragraph styling helpers ----------
def style_run(run, *, font=None, size_pt=None, bold=None, italic=None,
              color: RGBColor | None = None, all_caps=False, small_caps=False,
              tracking=None) -> None:
    if font:
        run.font.name = font
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color
    if all_caps:
        run.font.all_caps = True
    if small_caps:
        set_run_small_caps(run)
    if tracking is not None:
        set_run_letter_spacing(run, tracking)


def style_paragraph(p, *, alignment=None, space_before=None, space_after=None,
                    line_spacing=None, left_indent=None) -> None:
    pf = p.paragraph_format
    if alignment is not None:
        p.alignment = alignment
    if space_before is not None:
        pf.space_before = Pt(space_before)
    if space_after is not None:
        pf.space_after = Pt(space_after)
    if line_spacing is not None:
        pf.line_spacing = line_spacing
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    if left_indent is not None:
        pf.left_indent = Inches(left_indent)


__all__ = [
    "rgb",
    "PRIMARY", "ACCENT", "TEXT", "MUTED",
    "style_run", "style_paragraph",
    "_normalize_body_run",
]
