"""Parse a filled newsletter DOCX into a structured Newsletter object.

Sections are keyed by their numbered heading (1..7). The original section
names and content are preserved verbatim.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

log = logging.getLogger(__name__)


SECTION_HEAD_RE = re.compile(r"^\s*(\d+)\s*[\.\-—]?\s*[—-]?\s*(.+?)\s*$")
NUMBERED_HEAD_RE = re.compile(r"^\s*0?(\d+)\s+[—\-]\s+(.+?)\s*$")
LEGACY_HEAD_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")


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


@dataclass(frozen=True)
class BulletList:
    items: tuple[str, ...]  # each item is HTML-safe


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]  # rows of HTML cells
    has_header: bool


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


def _hyperlinks(paragraph: Paragraph) -> dict[str, str]:
    """Map relationship ids to URLs for hyperlinks in this paragraph."""
    out = {}
    for hl in paragraph._p.findall(qn("w:hyperlink")):
        rid = hl.get(qn("r:id"))
        if not rid:
            continue
        rel = paragraph.part.rels.get(rid)
        if rel is not None:
            out[rid] = rel.target_ref
    return out


def paragraph_to_html(paragraph: Paragraph) -> str:
    """Convert a paragraph's runs (and hyperlinks) into safe HTML."""
    rid_to_url = _hyperlinks(paragraph)

    parts: list[str] = []
    for child in paragraph._p.iterchildren():
        tag = child.tag
        if tag == qn("w:r"):
            for r in paragraph.runs:
                if r._r is child:
                    parts.append(_run_to_html(r))
                    break
        elif tag == qn("w:hyperlink"):
            url = rid_to_url.get(child.get(qn("r:id")), "")
            inner_runs = []
            for r_el in child.findall(qn("w:r")):
                # Build text manually since Paragraph.runs doesn't include
                # runs inside hyperlinks.
                texts = [t.text or "" for t in r_el.findall(qn("w:t"))]
                inner_runs.append(escape("".join(texts)))
            label = "".join(inner_runs) or escape(url)
            if url:
                parts.append(f'<a href="{escape(url, quote=True)}">{label}</a>')
            else:
                parts.append(label)
    return "".join(parts).strip()


# ---------- helpers ----------
def _is_list_paragraph(p: Paragraph) -> bool:
    return (p.style.name or "").startswith("List Paragraph")


def _has_image(p: Paragraph) -> list[str]:
    """Return list of relationship ids for embedded images in paragraph."""
    rids = []
    for blip in p._p.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        if rid:
            rids.append(rid)
    return rids


def _detect_section(text: str) -> tuple[int, str] | None:
    """Detect a section heading like '01 — RESEARCH' or '1. Research'."""
    m = NUMBERED_HEAD_RE.match(text)
    if m:
        return int(m.group(1)), m.group(2).strip()
    m = LEGACY_HEAD_RE.match(text)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None


SUBHEAD_TEXTS = frozenset({
    "Notable Publications", "Grants & Funding Awarded",
    "New Programs / Curriculum Updates", "New Partnerships & MOUs",
    "Visiting Scholars & Exchange", "Student Awards & Honors",
    "Thesis Defenses & Graduations", "Student Club & Community Activities",
    "New Faculty & Staff Welcome", "Deadlines & Notices",
})


# ---------- table → block ----------
def _table_to_block(table: Table) -> TableBlock:
    rows_out: list[tuple[str, ...]] = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cell_html_parts = []
            for p in cell.paragraphs:
                ph = paragraph_to_html(p)
                if ph:
                    cell_html_parts.append(ph)
            cells.append("<br>".join(cell_html_parts))
        rows_out.append(tuple(cells))
    # First row is header if all cells are short labels (heuristic: <= 30 chars
    # and bold dominant) — for safety we say it's a header.
    has_header = len(rows_out) >= 2
    return TableBlock(rows=tuple(rows_out), has_header=has_header)


# ---------- masthead extraction ----------
def _extract_masthead(doc: DocxDocument) -> Masthead:
    """Pull title/tagline/subtitle/issue line from the first table."""
    if not doc.tables:
        return Masthead("", "", "", "")
    cell = doc.tables[0].rows[0].cells[1]
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
    para_iter = iter(doc.paragraphs)
    table_iter = iter(doc.tables)
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
    """Parse a filled DOCX into a Newsletter."""
    doc = Document(str(docx_path))
    masthead = _extract_masthead(doc)

    sections: list[Section] = []
    current_num: int | None = None
    current_title: str = ""
    current_blocks: list[Block] = []
    pending_bullets: list[str] = []
    table_index = 0

    def flush_bullets():
        if pending_bullets:
            current_blocks.append(BulletList(items=tuple(pending_bullets)))
            pending_bullets.clear()

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
                continue
            flush_bullets()

            # Image inline in paragraph?
            for rid in _has_image(p):
                rel = p.part.rels.get(rid)
                fname = ""
                if rel is not None and rel.target_ref:
                    fname = Path(rel.target_ref).name
                current_blocks.append(ImageRef(rel_id=rid, filename=fname))

            # Subhead?
            if text in SUBHEAD_TEXTS:
                current_blocks.append(Heading(level=3, text=text))
                continue

            html = paragraph_to_html(p)
            if html:
                current_blocks.append(BodyParagraph(html=html))

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

    if len(sections) != 7:
        log.warning("Expected 7 sections, parsed %d", len(sections))

    return Newsletter(masthead=masthead, sections=tuple(sections))


__all__ = [
    "Newsletter", "Masthead", "Section", "Heading",
    "BodyParagraph", "BulletList", "TableBlock", "ImageRef",
    "parse", "paragraph_to_html",
]
