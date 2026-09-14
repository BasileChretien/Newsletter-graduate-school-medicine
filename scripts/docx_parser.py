"""Parse a filled newsletter DOCX into a structured Newsletter object.

Sections are keyed by their numbered heading (1..7). The original section
names and content are preserved verbatim.
"""

from __future__ import annotations

import logging
import re
import weakref
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from scripts.config import SUBHEAD_TEXTS  # known sub-headings (canonical template)
from scripts.text_utils import is_safe_url_scheme

log = logging.getLogger(__name__)


SECTION_HEAD_RE = re.compile(r"^\s*(\d+)\s*[\.\-—]?\s*[—-]?\s*(.+?)\s*$")
# `01 — TITLE` / `01 - TITLE` / `01. TITLE` / `01: TITLE` / fullwidth digits.
NUMBERED_HEAD_RE = re.compile(
    r"^\s*0?(\d+)\s*[—–\-:.]\s+(.+?)\s*$"
)
# Three alternative shapes for legacy / non-numbered-prefix section heads.
# The bare-numeric alternative REQUIRES an explicit separator -- without it
# `1 Recent grant from JSPS` (a body sentence beginning with a digit) would
# get mis-parsed as section 1 titled "Recent grant from JSPS".
#
#   1. English prose prefix: `Section 5: Title` / `Sec. 5 — Title`
#   2. Japanese: `第N章 Title` / `第N号 — Title` / `第N Title`
#      (the `第` prefix itself is the marker -- kanji suffix optional,
#      separator optional, since this form rarely uses ASCII punctuation)
#   3. Bare numeric: `1. Title` / `5: Title` / `7 — Title`
#      Separator is mandatory here.
LEGACY_HEAD_RE = re.compile(
    r"^\s*(?:"
    # English: "Section 5: Title" / "Sec. 5 — Title".
    # Separator IS required -- without it, "Section 5 research was
    # presented" (a body sentence starting with "Section") would
    # mis-classify as section 5 titled "research was presented".
    # The "Section" prefix is the marker; the separator preserves
    # the "this is a heading, not prose" intent.
    r"(?:Section|Sec\.?)\s+(?P<en_num>\d+)\s*[\.:—–\-]\s+"
    r"(?P<en_title>.+?)"
    r"|"
    # Japanese: 第N章/号/節 Title -- the 第 prefix IS the marker.
    # Both kanji suffix and separator optional, since this form
    # rarely uses ASCII punctuation and never accidentally appears
    # at the start of body prose in the same way.
    r"第\s*(?P<jp_num>\d+)\s*[章号節]?\s*[\.:—–\-]?\s*"
    r"(?P<jp_title>.+?)"
    r"|"
    # Bare numeric: separator REQUIRED (same reason as English).
    r"(?P<num>\d+)\s*[\.:—–\-]\s+(?P<title>.+?)"
    r")\s*$"
)


# ---------- block dataclasses ----------
@dataclass(frozen=True)
class HtmlText:
    """A piece of inline HTML (already escaped + with run formatting tags)."""

    html: str


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class BodyParagraph:
    html: str
    # CSS `text-align` from `paragraph_alignment`; "" is the default (left).
    align: str = ""


@dataclass(frozen=True)
class BulletList:
    items: tuple[str, ...]  # each item is HTML-safe
    # Per item, parallel to `items`. May be shorter (hand-built blocks);
    # a missing entry renders as the default.
    aligns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]  # rows of HTML cells
    has_header: bool
    # Per cell, parallel to `rows`; same "may be shorter" rule as bullets.
    aligns: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ImageRef:
    rel_id: str          # docx relationship id
    filename: str        # basename inside word/media/
    alt: str = ""
    url: str = ""        # public URL (filled by renderer after image extraction)


Block = BodyParagraph | BulletList | TableBlock | ImageRef | Heading


@dataclass(frozen=True)
class Section:
    number: int
    title: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Masthead:
    title: str
    tagline: str
    subtitle: str
    issue_line: str


@dataclass(frozen=True)
class Newsletter:
    masthead: Masthead
    sections: tuple[Section, ...]


# ---------- run → HTML ----------
def _run_to_html(run) -> str:
    text = escape(run.text or "")
    if not text:
        return ""
    if run.bold:
        text = f"<strong>{text}</strong>"
    if run.italic:
        text = f"<em>{text}</em>"
    return text


# ---------- paragraph alignment ----------
# Word's `w:jc` values, mapped onto the only `text-align` values that
# ever reach the email. An allowlist, not a pass-through: the value ends
# up inside a `style` attribute, and a DOCX is untrusted input. `left`
# and `start` are the email's default and deliberately absent -- an
# unaligned paragraph costs no bytes towards Gmail's clip threshold.
_JC_TO_CSS = {
    "both": "justify",
    "distribute": "justify",       # 均等割り付け
    "lowKashida": "justify",
    "mediumKashida": "justify",
    "highKashida": "justify",
    "thaiDistribute": "justify",
    "center": "center",
    "right": "right",
    "end": "right",
}

_W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
# Precompiled, with the style id bound as an XPath variable: a styleId is
# document-controlled text and is never spliced into the expression.
_STYLE_BY_ID = etree.XPath("w:style[@w:styleId = $sid]", namespaces=_W_NS)
_DEFAULT_PARAGRAPH_STYLE = etree.XPath(
    "w:style[@w:type = 'paragraph']"
    "[@w:default = '1' or @w:default = 'true' or @w:default = 'on']",
    namespaces=_W_NS,
)
_DEFAULT_TABLE_STYLE = etree.XPath(
    "w:style[@w:type = 'table']"
    "[@w:default = '1' or @w:default = 'true' or @w:default = 'on']",
    namespaces=_W_NS,
)
_DOC_DEFAULT_PPR = etree.XPath(
    "w:docDefaults/w:pPrDefault/w:pPr", namespaces=_W_NS)
_OVERRIDE_TABLE_JC = etree.XPath(
    "w:compat/w:compatSetting"
    "[@w:name = 'overrideTableStyleFontSizeAndJustification']/@w:val",
    namespaces=_W_NS,
)
_ON_VALUES = frozenset({"1", "true", "on"})

# Word nests `basedOn` a handful of levels deep. A longer chain is
# malformed, and a cycle (a style based on itself) would never end.
_MAX_STYLE_DEPTH = 32


def _jc_value(ppr) -> str | None:
    """`w:jc/@w:val` of a `w:pPr`, or None when it sets no alignment."""
    if ppr is None:
        return None
    jc = ppr.find(qn("w:jc"))
    return None if jc is None else (jc.get(qn("w:val")) or "")


def _last(elements):
    """The last match, or None. Where a document marks several styles of
    one type as the default, the last of them is the one used."""
    return elements[-1] if elements else None


def _style_chain(styles, style):
    """`style`, then each style it is `basedOn` -- most derived first."""
    seen: set[str] = set()
    for _ in range(_MAX_STYLE_DEPTH):
        if style is None:
            return
        own_id = style.get(qn("w:styleId")) or ""
        if own_id in seen:
            return
        seen.add(own_id)
        yield style
        based_on = style.find(qn("w:basedOn"))
        parent_id = based_on.get(qn("w:val")) if based_on is not None else None
        parents = _STYLE_BY_ID(styles, sid=parent_id) if parent_id else []
        style = parents[0] if parents else None


def _style_chain_jc(styles, style_id: str | None) -> str | None:
    """First alignment set by a paragraph style or a style it is based on.

    A paragraph with no `w:pStyle`, or one naming a style that does not
    exist, uses the document's default paragraph style -- as Word does.
    """
    found = _STYLE_BY_ID(styles, sid=style_id) if style_id else []
    start = found[0] if found else _last(_DEFAULT_PARAGRAPH_STYLE(styles))
    for style in _style_chain(styles, start):
        value = _jc_value(style.find(qn("w:pPr")))
        if value is not None:
            return value
    return None


# ---------- table-style alignment ----------
# A table style aligns text too: through its own paragraph properties, and
# through conditional formatting for the header row, first column, banded
# rows and so on (`w:tblStylePr`), which each table switches on with
# `w:tblLook`. Several of Word's built-in table styles centre a header row
# that way, with no paragraph alignment anywhere.
#
# Where Word and the letter of ECMA-376 disagree, this follows Word -- it
# is what the editor sees -- as Microsoft documents it in [MS-OI29500].

# Conditional formats in the order Word applies them, lowest first; where
# two apply to one cell and both set alignment, the later wins. ECMA-376
# lists column bands before row bands, and first/last row before
# first/last column; Word does the opposite of both, so a header row beats
# the first column where they meet, unless a corner format is set.
# `wholeTable` is left out on purpose: Word does not apply it, and the
# style's own `w:pPr` is the whole-table layer.
_CONDITION_ORDER = (
    "band1Horz", "band2Horz", "band1Vert", "band2Vert",
    "firstCol", "lastCol", "firstRow", "lastRow",
    "nwCell", "neCell", "swCell", "seCell",
)

# `w:tblLook` flags. Word reads the named attributes whenever any of them
# is present, and falls back to the older hex bitmask in `w:val` only
# when none is.
_LOOK_BITS = {
    "firstRow": 0x0020, "lastRow": 0x0040,
    "firstColumn": 0x0080, "lastColumn": 0x0100,
    "noHBand": 0x0200, "noVBand": 0x0400,
}
# A table with no `w:tblLook` at all: Word assumes header row and first
# column on, vertical banding off. (ECMA-376 says all off.)
_DEFAULT_LOOK = 0x04A0
# Word caps a band at 3 rows or columns. A missing band size is 0, which
# means no banding at all. (ECMA-376 says 1.)
_MAX_BAND_SIZE = 3


def _table_look(tbl_pr) -> frozenset[str]:
    """The `w:tblLook` flags switched on for a table."""
    look = tbl_pr.find(qn("w:tblLook")) if tbl_pr is not None else None
    if look is None:
        bits = _DEFAULT_LOOK
    else:
        named = {flag: look.get(qn(f"w:{flag}")) for flag in _LOOK_BITS}
        if any(value is not None for value in named.values()):
            return frozenset(
                flag for flag, value in named.items()
                if (value or "").lower() in _ON_VALUES)
        try:
            # Four hex digits hold every flag; anything longer is malformed
            # and must not cost an arbitrarily large integer parse.
            bits = int((look.get(qn("w:val")) or "0")[:8], 16)
        except ValueError:
            bits = 0
    return frozenset(flag for flag, bit in _LOOK_BITS.items() if bits & bit)


def _band_size(tbl_pr, axis: str) -> int | None:
    """`w:tblStyleRowBandSize` / `ColBandSize`, or None when not set."""
    el = tbl_pr.find(qn(f"w:tblStyle{axis}BandSize")) if tbl_pr is not None else None
    if el is None:
        return None
    value = el.get(qn("w:val")) or ""
    if not (value.isascii() and value.isdigit()) or len(value) > 4:
        return 0
    return min(int(value), _MAX_BAND_SIZE)


@dataclass(frozen=True)
class _TableStyle:
    """A table style's alignment settings, merged through `basedOn`."""

    base: str | None
    conditional: dict[str, str]
    row_band: int | None
    col_band: int | None


def _resolve_table_style(styles, style_id: str | None) -> _TableStyle | None:
    """Merge a table style with the styles it is based on, derived first.

    A table with no `w:tblStyle`, or one naming a style that does not
    exist, uses the document's default table style. Microsoft does not
    document how conditional formats inherit through `basedOn`; each is
    taken from the most derived style that sets it, the way every other
    style property inherits.
    """
    found = _STYLE_BY_ID(styles, sid=style_id) if style_id else []
    start = found[0] if found else _last(_DEFAULT_TABLE_STYLE(styles))
    if start is None:
        return None
    base: str | None = None
    conditional: dict[str, str] = {}
    row_band = col_band = None
    for style in _style_chain(styles, start):
        if base is None:
            base = _jc_value(style.find(qn("w:pPr")))
        for override in style.findall(qn("w:tblStylePr")):
            kind = override.get(qn("w:type"))
            if kind in _CONDITION_ORDER and kind not in conditional:
                value = _jc_value(override.find(qn("w:pPr")))
                if value is not None:
                    conditional[kind] = value
        tbl_pr = style.find(qn("w:tblPr"))
        if row_band is None:
            row_band = _band_size(tbl_pr, "Row")
        if col_band is None:
            col_band = _band_size(tbl_pr, "Col")
    return _TableStyle(base, conditional, row_band, col_band)


@dataclass(frozen=True)
class _TableAlignment:
    """One table's style, flags and band sizes: enough to align any cell."""

    style: _TableStyle
    look: frozenset[str]
    row_band: int
    col_band: int

    def cell_jc(self, row: int, col: int, n_rows: int, n_cols: int) -> str | None:
        """The `w:jc` the table style gives the cell at (row, col).

        `col` and `n_cols` count the row's `w:tc` cells, as LibreOffice
        does; merged cells (`w:gridSpan`) are not expanded to grid columns.
        """
        look = self.look
        first_row = "firstRow" in look and row == 0
        last_row = "lastRow" in look and row == n_rows - 1 and not first_row
        first_col = "firstColumn" in look and col == 0
        last_col = "lastColumn" in look and col == n_cols - 1 and not first_col
        active = {
            "firstRow": first_row, "lastRow": last_row,
            "firstCol": first_col, "lastCol": last_col,
            # A corner needs both of its edges switched on.
            "nwCell": first_row and first_col,
            "neCell": first_row and last_col,
            "swCell": last_row and first_col,
            "seCell": last_row and last_col,
        }
        # Header and total rows are not banded, and the count starts after
        # the header row, so the first body row is band 1. Columns likewise
        # with the first column.
        if "noHBand" not in look and self.row_band and not (first_row or last_row):
            band = (row - (1 if "firstRow" in look else 0)) // self.row_band
            active["band1Horz" if band % 2 == 0 else "band2Horz"] = True
        if "noVBand" not in look and self.col_band and not (first_col or last_col):
            band = (col - (1 if "firstColumn" in look else 0)) // self.col_band
            active["band1Vert" if band % 2 == 0 else "band2Vert"] = True
        jc = self.style.base
        for kind in _CONDITION_ORDER:
            if active.get(kind) and kind in self.style.conditional:
                jc = self.style.conditional[kind]
        return jc


# ---------- per-document memo ----------
@dataclass
class _DocumentAlignment:
    """What one document's styles resolve to, filled in as they are met."""

    styles: object
    doc_default: str | None
    default_style_id: str | None
    # Word's `overrideTableStyleFontSizeAndJustification` compatibility
    # setting -- see `_inherited_jc`.
    override_table_jc: bool
    # style id -> (alignment from its chain, is it the default style)
    paragraph_styles: dict[str | None, tuple[str | None, bool]] = field(
        default_factory=dict)
    table_styles: dict[str | None, _TableStyle | None] = field(
        default_factory=dict)


# Resolving a style walks its `basedOn` chain with an XPath lookup per
# step. Done per paragraph and per table cell, that made the 20,000-cell
# table cap ~6x slower to parse (0.85 s -> 5.1 s, measured) -- a visible
# stall in the browser build, where Pyodide runs CPython several times
# slower still. So each style is resolved once per document. Keyed weakly
# on the document part, so the entry goes when its document does: the
# browser tab builds many times over. Parsing never edits styles, so a
# memo taken at the first lookup stays true for the whole parse.
_DOCUMENT_ALIGNMENT: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _override_table_jc(part) -> bool:
    """Whether the document sets `overrideTableStyleFontSizeAndJustification`.

    Read through the relationship rather than python-docx's `settings`
    property, which adds an empty settings part to a document that has
    none.
    """
    try:
        settings = part.part_related_by(RT.SETTINGS).element
    except (AttributeError, KeyError):
        return False
    values = _OVERRIDE_TABLE_JC(settings)
    return bool(values) and str(values[-1]).lower() in _ON_VALUES


def _document_alignment(obj) -> _DocumentAlignment | None:
    """The memo for the document `obj` (a paragraph or a table) belongs to."""
    try:
        # A table built outside any document (`Table(tbl, None)`) has no
        # part at all -- and no styles either, so nothing is inherited.
        part = obj.part
    except AttributeError:
        return None
    cached = _DOCUMENT_ALIGNMENT.get(part)
    if cached is None:
        try:
            styles = part.styles.element
        except (AttributeError, KeyError, NotImplementedError):
            return None
        defaults = _DOC_DEFAULT_PPR(styles)
        default_style = _last(_DEFAULT_PARAGRAPH_STYLE(styles))
        cached = _DocumentAlignment(
            styles=styles,
            doc_default=_jc_value(defaults[0]) if defaults else None,
            default_style_id=(default_style.get(qn("w:styleId"))
                              if default_style is not None else None),
            override_table_jc=_override_table_jc(part),
        )
        _DOCUMENT_ALIGNMENT[part] = cached
    return cached


def _table_alignment(table: Table) -> _TableAlignment | None:
    """What aligns this table's cells, or None when nothing can."""
    memo = _document_alignment(table)
    if memo is None:
        return None
    tbl_pr = table._tbl.find(qn("w:tblPr"))
    style_el = tbl_pr.find(qn("w:tblStyle")) if tbl_pr is not None else None
    style_id = style_el.get(qn("w:val")) if style_el is not None else None
    if style_id not in memo.table_styles:
        memo.table_styles[style_id] = _resolve_table_style(memo.styles, style_id)
    style = memo.table_styles[style_id]
    if style is None:
        return None
    # A band size set on the table itself overrides its style's.
    row_band = _band_size(tbl_pr, "Row")
    col_band = _band_size(tbl_pr, "Col")
    return _TableAlignment(
        style=style,
        look=_table_look(tbl_pr),
        row_band=(style.row_band or 0) if row_band is None else row_band,
        col_band=(style.col_band or 0) if col_band is None else col_band,
    )


def _inherited_jc(paragraph: Paragraph, table_jc: str | None) -> str | None:
    """The `w:jc` a paragraph inherits when it sets none itself.

    ECMA-376 §17.7.2 order, most specific first: the paragraph style and
    its `basedOn` chain, then -- inside a table -- the table style, then
    the document defaults.
    """
    memo = _document_alignment(paragraph)
    if memo is None:
        return table_jc
    style_id = paragraph._p.style
    if style_id not in memo.paragraph_styles:
        memo.paragraph_styles[style_id] = (
            _style_chain_jc(memo.styles, style_id),
            not style_id or style_id == memo.default_style_id
            or not _STYLE_BY_ID(memo.styles, sid=style_id),
        )
    style_jc, in_default_style = memo.paragraph_styles[style_id]
    if style_jc is None:
        return memo.doc_default if table_jc is None else table_jc
    # Word's compatibility rule, in force unless the document opts out
    # with `overrideTableStyleFontSizeAndJustification` (Word 2013 and
    # later write it): LEFT set by the default paragraph style does not
    # override the table style's alignment. It covers the default style
    # itself, not styles based on it.
    if (table_jc is not None and in_default_style
            and not memo.override_table_jc
            and style_jc in ("left", "start")):
        return table_jc
    return style_jc


def paragraph_alignment(paragraph: Paragraph,
                        table_jc: str | None = None) -> str:
    """The paragraph's effective alignment as a CSS `text-align` value.

    Resolved the way Word resolves it: direct formatting first, then the
    paragraph style and its `basedOn` chain, then -- for a paragraph in a
    table -- the table style, then the document defaults. `table_jc` is
    the table style's value for the paragraph's cell; it depends on where
    the cell sits (header row, banding...), so `_table_to_block`, which
    knows the position, works it out and passes it in.

    Returns "justify", "center" or "right" -- or "" for left, start and
    unset, which is what the stylesheet already renders.

    Reported from the field: this was never read, so justified text came
    out ragged-right. Word set up for Japanese justifies body text by
    default (両端揃え); the issue that exposed it had 106 of its 125
    paragraphs justified, and its photo captions centred.

    Not consulted: a list's numbering level, and right-to-left paragraphs
    (`w:bidi`), which would flip `start` / `end` -- this newsletter is
    Japanese and English.
    """
    value = _jc_value(paragraph._p.pPr)
    if value is None:
        value = _inherited_jc(paragraph, table_jc)
    return _JC_TO_CSS.get(value or "", "")


def _has_text(html: str) -> bool:
    """True when `html` shows any text, rather than only a picture."""
    return bool(re.sub(r"<[^>]*>", "", html).strip())


# ---------- inline image (drawing → <img>) ----------
DRAWING_TAG = qn("w:drawing")
BLIP_TAG = qn("a:blip")
EMBED_ATTR = qn("r:embed")
EXTENT_TAG = qn("wp:extent")
PIC_CNVPR_TAG = qn("pic:cNvPr")

# EMU per pixel at 96 dpi (914400 EMU / inch / 96 px / inch).
EMU_PER_PX = 9525
# Cap image width to fit the 600 px email container with padding.
MAX_IMG_PX = 560
# A picture's horizontal placement, by its paragraph's alignment.
# Pictures are `display:block`, and a block is not moved by its parent's
# `text-align` in Gmail or Apple Mail -- only auto margins move it.
# Outlook's Word engine is the reverse (ignores the margins, honours
# `text-align` on the paragraph), so a centred photo relies on both.
_IMG_MARGIN = {"center": "0 auto", "right": "0 0 0 auto"}


def _drawing_to_img(drawing, part, align: str = "") -> str:
    """Return an <img> tag (with media:// sentinel src) for a w:drawing.

    `align` is the paragraph's `paragraph_alignment` value; see
    `_IMG_MARGIN` for why a picture needs it separately from the text.
    """
    blip = drawing.find(".//" + BLIP_TAG)
    if blip is None:
        return ""
    rid = blip.get(EMBED_ATTR)
    if not rid:
        return ""
    rel = part.rels.get(rid)
    if rel is None or not rel.target_ref:
        return ""
    fname = Path(rel.target_ref).name

    # Optional alt text from pic:cNvPr@descr or @name.
    alt = ""
    cnv_pr = drawing.find(".//" + PIC_CNVPR_TAG)
    if cnv_pr is not None:
        alt = cnv_pr.get("descr") or cnv_pr.get("name") or ""

    # Width and height from wp:extent (in EMU). Cap width to MAX_IMG_PX
    # and scale height proportionally so Outlook (which ignores
    # `height:auto`) reserves the right vertical space even when images
    # are blocked.
    size_attrs = ""
    extent = drawing.find(".//" + EXTENT_TAG)
    if extent is not None:
        cx_str, cy_str = extent.get("cx"), extent.get("cy")
        if cx_str and cx_str.isdigit():
            cx = int(cx_str)
            width_px = max(1, min(cx // EMU_PER_PX, MAX_IMG_PX))
            size_attrs = f' width="{width_px}"'
            if cy_str and cy_str.isdigit():
                cy = int(cy_str)
                # Scale height proportionally if width was capped.
                ratio = width_px / (cx / EMU_PER_PX)
                height_px = max(1, int(cy / EMU_PER_PX * ratio))
                size_attrs += f' height="{height_px}"'

    return (
        f'<img src="media://{escape(fname, quote=True)}" '
        f'alt="{escape(alt, quote=True)}"{size_attrs} '
        f'style="display:block;max-width:100%;height:auto;'
        f'margin:{_IMG_MARGIN.get(align, "0")};border:0;" />'
    )


def _hyperlinks(paragraph: Paragraph) -> dict[str, str]:
    """Map relationship ids to URLs for hyperlinks in this paragraph."""
    out = {}
    # `.//` rather than direct children: a link added with Track
    # Changes on sits inside `<w:ins>`, and the direct search missed
    # it, so the URL map came back empty and the anchor lost its href.
    for hl in paragraph._p.findall(".//" + qn("w:hyperlink")):
        rid = hl.get(qn("r:id"))
        if not rid:
            continue
        rel = paragraph.part.rels.get(rid)
        if rel is not None:
            out[rid] = rel.target_ref
    return out


def _iter_content_children(element):
    """Yield a paragraph's content children, resolving tracked changes.

    Word wraps edits made with Track Changes turned on:

      * `<w:ins>`      -- inserted content. It IS in the document as the
                          author sees it, so we descend into it.
      * `<w:moveTo>`   -- the destination of moved content. Also present.
      * `<w:del>`      -- deleted content. Its text lives in `<w:delText>`
                          and must NEVER be published: someone struck a
                          sentence out, and printing it in a newsletter
                          that goes to ~50 people would be worse than
                          dropping it.
      * `<w:moveFrom>` -- the origin of moved content; same reasoning.

    Only `w:r` children were handled before, so anything inside `w:ins`
    was silently dropped -- the run was not a direct child, so the loop
    never saw it. In the reported document that cost the dean's photo
    and a large section photo, both of which had been added with Track
    Changes on and never accepted. Text inserted the same way would have
    vanished just as quietly, which is the more dangerous version of
    this bug: a missing photo is visible, a missing sentence is not.

    Deletions are excluded here deliberately and explicitly. They were
    excluded before too, but only as a side effect of the tag check --
    which means nobody had decided it, and the next person to widen the
    traversal could easily have started publishing struck-out text.
    """
    # Iterative rather than recursive, on an explicit stack. Nested
    # wrappers are bounded today -- libxml2 refuses documents deeper than
    # 256 elements and python-docx does not pass `XML_PARSE_HUGE`, so the
    # deepest `w:ins` chain that can reach this function is 254, measured
    # -- but that bound is an undocumented default of a transitive
    # dependency, not a decision this file made. Growing on the heap
    # instead of the C call stack means it stays correct if anyone ever
    # sets `huge_tree`.
    #
    # Note this is NOT the same situation as `_row_cells`: that recursion
    # (`_tc_above`) scales with the number of sibling ROWS, which no
    # nesting cap bounds, which is why a ~3000-row `w:vMerge` chain really
    # did raise `RecursionError`.
    stack = [element.iterchildren()]
    while stack:
        child = next(stack[-1], None)
        if child is None:
            stack.pop()
            continue
        tag = child.tag
        if tag in (qn("w:ins"), qn("w:moveTo")):
            stack.append(child.iterchildren())
        elif tag in (qn("w:del"), qn("w:moveFrom")):
            continue
        else:
            yield child


def paragraph_to_html(paragraph: Paragraph, table_jc: str | None = None) -> str:
    """Convert a paragraph's runs (and hyperlinks) into safe HTML.

    `table_jc` is what the table style gives this paragraph's cell, for a
    paragraph in a table -- see `paragraph_alignment`.
    """
    rid_to_url = _hyperlinks(paragraph)
    # Resolved only when a picture needs it: most paragraphs have none,
    # and their alignment travels on the block instead.
    align: str | None = None

    parts: list[str] = []
    for child in _iter_content_children(paragraph._p):
        tag = child.tag
        if tag == qn("w:r"):
            # Inline drawing inside this run? Emit an <img> tag.
            drawing = child.find(".//" + DRAWING_TAG)
            if drawing is not None:
                if align is None:
                    align = paragraph_alignment(paragraph, table_jc)
                img = _drawing_to_img(drawing, paragraph.part, align)
                if img:
                    parts.append(img)
                    continue
            # Build the Run directly rather than looking it up in
            # `paragraph.runs`: that property lists only DIRECT `w:r`
            # children, so a run inside `<w:ins>` would never match and
            # its text would still be lost after the traversal fix.
            parts.append(_run_to_html(Run(child, paragraph)))
        elif tag == qn("w:hyperlink"):
            url = rid_to_url.get(child.get(qn("r:id")), "")
            inner_runs = []
            for r_el in child.findall(qn("w:r")):
                # Build text manually since Paragraph.runs doesn't include
                # runs inside hyperlinks.
                texts = [t.text or "" for t in r_el.findall(qn("w:t"))]
                inner_runs.append(escape("".join(texts)))
            label = "".join(inner_runs) or escape(url)
            if url and is_safe_url_scheme(url):
                parts.append(f'<a href="{escape(url, quote=True)}">{label}</a>')
            elif url:
                # Unsafe scheme: keep the words, drop the target. Escaping
                # alone was never enough here -- it stops an attribute
                # breakout but says nothing about WHERE the link goes, and
                # this anchor is what ~50 recipients click in a mail that
                # passes SPF/DKIM/DMARC because it came from the editor's
                # own mailbox. `file://host/share/x` is a UNC path in
                # Outlook: one click authenticates the recipient's machine
                # to the attacker over SMB.
                #
                # The label is preserved rather than deleted so the
                # sentence still reads, and `validator.py` reports the
                # dropped target so the editor learns their document
                # contained one instead of silently losing a link they
                # meant to include.
                log.warning(
                    "Dropped a link with an unsupported address type: %r "
                    "(only http, https and mailto are sent to recipients).",
                    url[:120],
                )
                # The marker carries NO href. An early version put the
                # rejected URL in a `data-` attribute so the validator
                # could name it -- which would have shipped the
                # attacker's string into ~50 mailboxes as inert text, for
                # no benefit to the person who needs it. The editor gets
                # the URL on the console via the warning above; the
                # message itself carries only a count.
                parts.append(f'{label}<span class="meridian-dropped-link"></span>')
            else:
                parts.append(label)
    return "".join(parts).strip()


# ---------- helpers ----------
def _is_list_paragraph(p: Paragraph) -> bool:
    return (p.style.name or "").startswith("List Paragraph")


# A real section number is one or two digits. The cap exists because
# CPython 3.11+ raises `ValueError: Exceeds the limit (4300 digits) for
# integer string conversion`, so a paragraph of 5000 digits followed by
# ". Boom" crashed the parse with a traceback the editor could not act
# on -- and a 4000-digit one succeeded, rendering a 4000-digit number.
_MAX_SECTION_DIGITS = 4


def _detect_section(text: str) -> tuple[int, str] | None:
    """Detect a section heading like '01 — RESEARCH' or '1. Research'.

    Tries the strict numeric pattern first; falls back to the legacy
    pattern that supports English `Section N` and Japanese `第N章`
    prefixes plus a separator-required bare-numeric form.
    """
    m = NUMBERED_HEAD_RE.match(text)
    if m:
        if len(m.group(1)) > _MAX_SECTION_DIGITS:
            return None
        return int(m.group(1)), m.group(2).strip()
    m = LEGACY_HEAD_RE.match(text)
    if m:
        num = m.group("en_num") or m.group("jp_num") or m.group("num")
        title = (m.group("en_title") or m.group("jp_title")
                 or m.group("title") or "")
        if num and title.strip():
            if len(num) > _MAX_SECTION_DIGITS:
                return None
            return int(num), title.strip()
    return None


# Maximum text length for a paragraph to be treated as a sub-heading via
# the structural heuristic. Prevents long sentences from being mistaken
# for headings just because they're bold.
_SUBHEAD_MAX_CHARS = 80


def is_subheading_paragraph(p: Paragraph, text: str | None = None) -> bool:
    """Decide whether a paragraph is a sub-heading.

    Detection is purely structural so editors can add / rename / remove
    sub-sections in Word and the toolkit picks them up automatically:

      1. Word's built-in `Heading 2` / `Heading 3` / ... styles.
      2. Backwards-compat: text exactly matches one of `SUBHEAD_TEXTS`.
      3. Short, all-bold paragraph that doesn't end like a sentence.

    Section-level headings ("1. ..." / "01 — ...") are detected
    separately in `_detect_section` and short-circuit before we get here.

    `text` is optional -- if not supplied we derive it from `p.text.strip()`.
    Pass it when you already have it to save one strip() call.
    """
    if text is None:
        text = p.text.strip()
    if not text or len(text) > _SUBHEAD_MAX_CHARS:
        return False

    # 1. Word built-in heading style (Heading 2/3/... -- never Heading 1
    # which we reserve for section headings).
    # `style_id` is the locale-invariant Word identifier
    # ("Heading2", "Heading3"...). `style.name` is localized
    # ("見出し 2", "Überschrift 2"). Prefer style_id; fall back to name.
    style = p.style
    style_id = getattr(style, "style_id", None) or ""
    style_name = (getattr(style, "name", "") or "")
    if style_id.startswith("Heading") and style_id != "Heading1":
        return True
    if style_name.startswith("Heading") and not style_name.endswith(" 1"):
        return True

    # 2. Backwards-compat: hard-coded list of canonical sub-headings.
    if text in SUBHEAD_TEXTS:
        return True

    # 3. Heuristic: short bold paragraph without sentence punctuation.
    runs_with_text = [r for r in p.runs if r.text.strip()]
    if not runs_with_text:
        return False
    if not all(bool(r.bold) for r in runs_with_text):
        return False
    if text.endswith((".", "!", "?", "…", "...")):
        return False
    # Avoid catching a single bold word inside a normal paragraph -- a
    # sub-head is usually a complete short label.
    if len(text) < 3:
        return False
    return True


# ---------- table geometry limits ----------
#
# python-docx's `_Row.cells` expands `w:gridSpan` eagerly -- it yields the
# same cell `grid_span` times -- and `grid_span` is an unbounded Python
# int straight out of attacker-controlled XML. A 1.4 KB DOCX declaring
# `w:gridSpan w:val="50000000"` costs minutes of CPU and hundreds of MB
# before anything is rendered. `_Row.cells` also walks `_tc_above`
# recursively for every `w:vMerge="continue"` row, which is quadratic in
# the run length and ends in `RecursionError`.
#
# Both are reached from `_extract_masthead`, which runs on EVERY document
# before any parsing decision -- so the payload needs nothing but a first
# table. In the browser build this pins the only worker thread and the
# tab simply stops responding.
#
# `_row_cells` sidesteps both by reading the row's own `tc` elements
# directly: no span expansion, no vertical-merge recursion. A merged cell
# is emitted once rather than N times, which is what an HTML email wants
# anyway -- the 600 px layout cannot render 64 columns, let alone 50
# million.
MAX_TABLE_COLS = 64
MAX_TABLE_ROWS = 500
MAX_TABLE_CELLS_TOTAL = 20_000


def _row_cells(row) -> list:
    """Cells of `row` without `gridSpan` expansion or merge recursion."""
    from docx.table import _Cell

    tcs = row._tr.tc_lst[:MAX_TABLE_COLS]
    return [_Cell(tc, row.table) for tc in tcs]


# ---------- table → block ----------
def _table_to_block(table: Table) -> TableBlock:
    rows_out: list[tuple[str, ...]] = []
    aligns_out: list[tuple[str, ...]] = []
    # The row and column caps bound each dimension separately, so on
    # their own they still admit 500 x 64 = 32,000 cells -- more than the
    # 20,000 total this file declares. The total is the one that matters:
    # cost is per cell (each runs `paragraph_to_html` over its
    # paragraphs), not per row or per column.
    budget = MAX_TABLE_CELLS_TOTAL
    # What the table style gives a cell depends on where the cell sits
    # (header row, first column, banding), so it is worked out here, where
    # the position is known, and handed to each paragraph in the cell.
    table_alignment = _table_alignment(table)
    n_rows = len(table._tbl.tr_lst)
    for r, row in enumerate(table.rows[:MAX_TABLE_ROWS]):
        if budget <= 0:
            break
        cells = []
        cell_aligns = []
        n_cols = len(row._tr.tc_lst)
        for c, cell in enumerate(_row_cells(row)[:budget]):
            table_jc = (table_alignment.cell_jc(r, c, n_rows, n_cols)
                        if table_alignment is not None else None)
            cell_html_parts = []
            # One `text-align` per cell, taken from the paragraphs that
            # carry text (a picture paragraph places itself with margins)
            # and kept only when they agree: a cell mixing centred and
            # justified text has no single right answer, so it keeps the
            # default rather than guessing.
            text_aligns = set()
            for p in cell.paragraphs:
                ph = paragraph_to_html(p, table_jc)
                if ph:
                    cell_html_parts.append(ph)
                    if _has_text(ph):
                        text_aligns.add(paragraph_alignment(p, table_jc))
            cells.append("<br>".join(cell_html_parts))
            cell_aligns.append(
                next(iter(text_aligns)) if len(text_aligns) == 1 else "")
        budget -= len(cells)
        rows_out.append(tuple(cells))
        aligns_out.append(tuple(cell_aligns))
    # First row is header if all cells are short labels (heuristic: <= 30 chars
    # and bold dominant) — for safety we say it's a header.
    has_header = len(rows_out) >= 2
    return TableBlock(rows=tuple(rows_out), has_header=has_header,
                      aligns=tuple(aligns_out))


# ---------- masthead extraction ----------
def _extract_masthead(doc: DocxDocument) -> Masthead:
    """Pull title/tagline/subtitle/issue line from the first table."""
    if not doc.tables:
        return Masthead("", "", "", "")
    # The template's masthead is a 2-column table, but this runs on EVERY
    # document before the strict/lenient decision -- so an ordinary Word
    # file whose first table is a one-column layout box (very common)
    # raised `IndexError: tuple index out of range` and the editor got a
    # bare traceback. That defeated the whole point of v1.1.2's lenient
    # parse, which exists to accept arbitrary documents.
    rows = doc.tables[0].rows
    if not rows:
        return Masthead("", "", "", "")
    cells = _row_cells(rows[0])
    if len(cells) < 2:
        return Masthead("", "", "", "")
    cell = cells[1]
    paragraphs = [p.text.strip() for p in cell.paragraphs if p.text.strip()]
    title = paragraphs[0] if paragraphs else ""
    tagline = paragraphs[1] if len(paragraphs) > 1 else ""
    subtitle = paragraphs[2] if len(paragraphs) > 2 else ""
    issue_line = paragraphs[3] if len(paragraphs) > 3 else ""
    return Masthead(title, tagline, subtitle, issue_line)


# ---------- main parse ----------
def _iter_body_blocks(doc: DocxDocument) -> Iterable[tuple[str, object]]:
    """Yield ('paragraph', Paragraph) or ('table', Table) in document order."""
    body = doc.element.body
    paragraphs = list(doc.paragraphs)
    tables = list(doc.tables)
    p_idx = 0
    t_idx = 0
    for child in body.iterchildren():
        if child.tag == qn("w:p") and p_idx < len(paragraphs):
            yield "paragraph", paragraphs[p_idx]
            p_idx += 1
        elif child.tag == qn("w:tbl") and t_idx < len(tables):
            yield "table", tables[t_idx]
            t_idx += 1


def parse(docx_path: Path) -> Newsletter:
    """Parse a filled DOCX into a Newsletter.

    Two parse passes:
      1. **Strict pass** -- look for numbered section headings
         (`1. Title`, `Section 5: Title`, `第3章 Title`, ...) and
         organise paragraphs/tables/images under them. This is the
         canonical layout the bundled MERIDIAN template uses.
      2. **Lenient fallback** -- if pass 1 finds zero sections, the
         user is sending an arbitrary DOCX (not the MERIDIAN
         template). Re-walk the body, treating EVERYTHING as one
         synthetic Section(number=1, title="Newsletter"). Word's
         Heading-1 paragraphs become section dividers; everything
         else is body content. Without this fallback the parser
         silently dropped non-template DOCX content and the editor
         got a blank email -- the production-bug report from the
         field trial that prompted this rewrite.
    """
    doc = Document(str(docx_path))
    masthead = _extract_masthead(doc)

    sections = _parse_strict(doc)
    if not sections:
        log.warning(
            "No numbered section headings detected in %s. Falling back "
            "to lenient parse: the entire document body is rendered as "
            "one section. To get the structured multi-section layout, "
            "use the MERIDIAN template (or add headings like "
            "'1. Title', 'Section 1: Title', or '第1章 Title' to your "
            "document).",
            docx_path,
        )
        sections = _parse_lenient(doc)

    log.debug("Parsed %d section(s)", len(sections))
    return Newsletter(masthead=masthead, sections=tuple(sections))


def _parse_strict(doc: DocxDocument) -> list[Section]:
    """Original strict parser: requires numbered section headings."""
    sections: list[Section] = []
    current_num: int | None = None
    current_title: str = ""
    current_blocks: list[Block] = []
    pending_bullets: list[str] = []
    pending_aligns: list[str] = []
    table_index = 0

    def flush_bullets():
        if pending_bullets:
            current_blocks.append(BulletList(items=tuple(pending_bullets),
                                             aligns=tuple(pending_aligns)))
            pending_bullets.clear()
            pending_aligns.clear()

    def flush_section():
        nonlocal current_num, current_title, current_blocks
        if current_num is not None:
            sections.append(Section(
                number=current_num,
                title=current_title,
                blocks=tuple(current_blocks),
            ))
        current_blocks = []

    for kind, item in _iter_body_blocks(doc):
        if kind == "paragraph":
            p: Paragraph = item
            text = p.text.strip()
            sec = _detect_section(text)
            if sec is not None:
                flush_bullets()
                flush_section()
                current_num, current_title = sec
                continue
            if current_num is None:
                continue  # pre-section content (masthead is in tables[0])

            # Bullet list?
            if _is_list_paragraph(p):
                html = paragraph_to_html(p)
                if html:
                    pending_bullets.append(html)
                    pending_aligns.append(paragraph_alignment(p))
                continue
            flush_bullets()

            # Subhead? (Word style + heuristic + canonical-template list)
            if is_subheading_paragraph(p, text):
                current_blocks.append(Heading(level=3, text=text))
                continue

            # `paragraph_to_html` now embeds inline images directly via
            # media:// sentinel URLs, so a stand-alone image paragraph
            # renders as <img> inside the body paragraph.
            html = paragraph_to_html(p)
            if html:
                current_blocks.append(BodyParagraph(
                    html=html, align=paragraph_alignment(p)))

        else:  # table
            t: Table = item
            table_index += 1
            if table_index == 1:
                continue  # masthead table — already extracted
            if current_num is None:
                continue
            flush_bullets()
            current_blocks.append(_table_to_block(t))

    flush_bullets()
    flush_section()
    return sections


def _parse_lenient(doc: DocxDocument) -> list[Section]:
    """Fallback parser for DOCX files that don't use numbered section
    headings (i.e. arbitrary user-supplied DOCX, not the MERIDIAN
    template). Treats the whole body as ONE Section -- numbered 1
    so the renderer doesn't display a "Section 0" placeholder.

    Word `Heading 1` paragraphs become inline H2 markers (visual
    section breaks within the single section); `Heading 2` becomes
    H3 sub-headings. Body text, bullet lists, tables, and images
    are emitted as-is.

    Round-17 production-bug fix: the user's first real-world test
    used their own DOCX (no MERIDIAN headings) and got an empty
    email -- because the strict parser silently dropped every
    paragraph until it saw a numbered heading, which never came.
    """
    blocks: list[Block] = []
    pending_bullets: list[str] = []
    pending_aligns: list[str] = []
    table_index = 0

    def flush_bullets():
        if pending_bullets:
            blocks.append(BulletList(items=tuple(pending_bullets),
                                     aligns=tuple(pending_aligns)))
            pending_bullets.clear()
            pending_aligns.clear()

    for kind, item in _iter_body_blocks(doc):
        if kind == "paragraph":
            p: Paragraph = item
            text = p.text.strip()
            if not text:
                # Empty paragraphs aren't worth carrying through, but
                # might still hold an inline image. Let
                # `paragraph_to_html` decide.
                html = paragraph_to_html(p)
                if html:
                    flush_bullets()
                    blocks.append(BodyParagraph(html=html, align=paragraph_alignment(p)))
                continue

            # Word-style heading detection -- promote to visual
            # divider. Heading 1 -> H2 (we already use H1 for the
            # masthead-substitute); Heading 2 -> H3.
            style_name = ""
            if p.style is not None and p.style.name:
                style_name = p.style.name.lower()
            if "heading 1" in style_name:
                flush_bullets()
                blocks.append(Heading(level=2, text=text))
                continue
            if "heading 2" in style_name or "heading 3" in style_name:
                flush_bullets()
                blocks.append(Heading(level=3, text=text))
                continue

            if _is_list_paragraph(p):
                html = paragraph_to_html(p)
                if html:
                    pending_bullets.append(html)
                    pending_aligns.append(paragraph_alignment(p))
                continue
            flush_bullets()

            html = paragraph_to_html(p)
            if html:
                blocks.append(BodyParagraph(html=html, align=paragraph_alignment(p)))

        else:  # table
            t: Table = item
            table_index += 1
            if table_index == 1:
                # Skip ONLY if it looks like a masthead (3 rows, no
                # data-table feel). For arbitrary DOCX the first
                # table is usually real content -- keep it.
                if _looks_like_masthead(t):
                    continue
            flush_bullets()
            blocks.append(_table_to_block(t))

    flush_bullets()

    # Emit a single synthetic section so the renderer has something
    # non-empty to traverse. Title is "Newsletter" rather than empty
    # so the rendered HTML doesn't have a bare section break.
    if not blocks:
        return []
    return [Section(number=1, title="Newsletter", blocks=tuple(blocks))]


def _looks_like_masthead(t: Table) -> bool:
    """Heuristic: does this table look like the MERIDIAN masthead
    (3 rows, mostly empty, used for layout)?

    Used by the lenient fallback parser to decide whether to skip
    the first table (canonical template) or render it as content
    (arbitrary user DOCX with a real data table on page 1).
    """
    if len(t.rows) != 3:
        return False
    # Masthead has at most a handful of short text cells; a real
    # data table typically has more rows or longer cell content.
    total_chars = sum(
        len(cell.text) for row in t.rows for cell in _row_cells(row)
    )
    return total_chars < 400


__all__ = [
    "Newsletter", "Masthead", "Section", "Heading",
    "BodyParagraph", "BulletList", "TableBlock", "ImageRef",
    "parse", "paragraph_alignment", "paragraph_to_html",
    "is_subheading_paragraph",
]
