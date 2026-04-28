"""HTML -> plaintext conversion for the multipart/alternative body.

Most corporate spam filters (Mimecast, Proofpoint, Microsoft Defender,
Barracuda) score HTML-only mail higher than `multipart/alternative`,
and they also score the *ratio* of plaintext to HTML -- a one-line
plaintext alongside 33 KB of HTML still triggers "HTML-heavy" rules.
So we don't just produce *some* plaintext; we produce **structurally
preserved** plaintext: heading markers, bullet glyphs, link URLs.

Conversion rules:

* Block elements (`<p>`, `<h1..h6>`, `<tr>`, `<li>`, `<br>`, `<div>`)
  produce line breaks. Outlook's COM `Body` setter will normalize
  `\\n` to `\\r\\n` when serializing the MIME, so we don't need to.
* `<h1>` / `<h2>` -> `=== HEADING ===` (eye-catching for plaintext readers
  AND clearly heading-shaped to spam-filter heuristics that score
  unstructured plaintext lower).
* `<h3>` / `<h4>` / `<h5>` / `<h6>` -> `--- subheading ---`
* `<li>` -> `• ` (bullet glyph) prefix.
* Hyperlinks: `<a href="X">label</a>` -> `label (X)` so the URL is
  visible to plaintext readers.
* Whitespace runs collapse to single space (preserves line structure
  by working line-by-line).
* All HTML comments are stripped.
* Hidden elements (display:none / visibility:hidden / hidden attribute)
  drop entirely -- recipient invisibility carries through to plaintext.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from scripts.html_utils import remove_hidden_elements


_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "hr", "section", "article", "header", "footer",
    "thead", "tbody", "tfoot",
})

_DROP_TAGS: frozenset[str] = frozenset({
    "script", "style", "head", "meta", "link",
})

# URL schemes safe to surface to plaintext readers. Anything outside
# this set is dropped (the link's label survives, the URL doesn't) so
# `javascript:`, `data:`, `file:///`, `tel:`, etc. can't be smuggled.
_SAFE_URL_SCHEMES: tuple[str, ...] = ("http://", "https://", "mailto:")

# Heading + sub-heading markers chosen to read well in plaintext AND to
# clearly look heading-shaped to spam-filter heuristics that score
# unstructured plaintext lower (Mimecast, Proofpoint).
_H_MAJOR_PREFIX = "=== "
_H_MAJOR_SUFFIX = " ==="
_H_MINOR_PREFIX = "--- "
_H_MINOR_SUFFIX = " ---"

# Bullet glyph for <li>. U+2022 BULLET renders cleanly in monospace
# plaintext readers and adds a recognisable list-shape to spam scoring.
_BULLET = "• "


def _normalize_line(line: str) -> str:
    r"""Collapse all in-line whitespace runs to a single ASCII space.

    Includes NBSP (U+00A0) -- Word's auto-format substitutes NBSP for
    ASCII space when text is pasted, and we want the plaintext output
    to read with normal spacing. Use the explicit `\u00a0` escape
    rather than a literal NBSP byte, so a future editor reformatting
    this line can't silently strip it.
    """
    return re.sub(r"[ \t\u00a0]+", " ", line).strip()


def html_to_plaintext(html: str) -> str:
    """Convert an HTML string to a readable, spam-friendly plaintext.

    Output is suitable for `multipart/alternative` text part: visible
    URLs after link text, heading / subhead markers, bullet glyphs,
    line-broken on block boundaries, no HTML artefacts.

    Never raises in practice -- malformed HTML is handled gracefully
    by BeautifulSoup. The Outlook backend still wraps the call in a
    try/except as belt-and-braces.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Drop tags whose text we never want in the plaintext (script
    # body, CSS rules, head metadata).
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Drop hidden elements -- recipient-invisible -> plaintext-invisible.
    # Shared helper so this list stays in lockstep with the validator's
    # masthead-guard (round-9 code-review HIGH).
    remove_hidden_elements(soup)

    # Wrap headings with marker prefixes/suffixes (before block-newline
    # injection so the markers travel with the heading text).
    for h in soup.find_all(["h1", "h2"]):
        if h.string is None:
            label = h.get_text(" ", strip=True)
            h.clear()
            h.append(NavigableString(
                f"{_H_MAJOR_PREFIX}{label.upper()}{_H_MAJOR_SUFFIX}"
            ))
        else:
            h.string = f"{_H_MAJOR_PREFIX}{h.string.strip().upper()}{_H_MAJOR_SUFFIX}"
    for h in soup.find_all(["h3", "h4", "h5", "h6"]):
        if h.string is None:
            label = h.get_text(" ", strip=True)
            h.clear()
            h.append(NavigableString(
                f"{_H_MINOR_PREFIX}{label}{_H_MINOR_SUFFIX}"
            ))
        else:
            h.string = f"{_H_MINOR_PREFIX}{h.string.strip()}{_H_MINOR_SUFFIX}"

    # Prefix list items with a bullet glyph.
    for li in soup.find_all("li"):
        li.insert(0, NavigableString(_BULLET))

    # Replace <a href="X">label</a> with "label (X)" so plaintext
    # readers can copy / click the URL. Drop unsafe schemes.
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        label = a.get_text(" ", strip=True)
        if href and href.startswith(_SAFE_URL_SCHEMES):
            if label and label != href:
                a.replace_with(f"{label} ({href})")
            else:
                a.replace_with(href)
        else:
            # Unsafe scheme or empty href -- preserve the visible label
            # only. Never expose `javascript:` / `data:` / `file:///`.
            a.replace_with(label)

    # Insert newline markers around block-level tags before pulling text.
    for tag in soup.find_all(True):
        if tag.name in _BLOCK_TAGS:
            tag.insert_before(NavigableString("\n"))
            tag.insert_after(NavigableString("\n"))

    raw = soup.get_text(separator="")

    # Collapse whitespace within each line, then collapse runs of >2
    # blank lines into exactly one blank line.
    lines = [_normalize_line(ln) for ln in raw.splitlines()]
    out: list[str] = []
    blank_run = 0
    for ln in lines:
        if not ln:
            blank_run += 1
            if blank_run <= 1:
                out.append("")
        else:
            blank_run = 0
            out.append(ln)
    return "\n".join(out).strip() + "\n"


def html_to_plaintext_strict_fallback(html: str) -> str:
    """Last-resort plaintext conversion used when `html_to_plaintext`
    raises (which shouldn't happen, but Outlook drafts are a bad place
    to discover an unhandled exception). Strips every tag with a
    regex; not pretty, but it produces a real plaintext alternative
    so the MIME message stays `multipart/alternative` rather than
    HTML-only.
    """
    no_tags = re.sub(r"<[^>]+>", "", html)
    return _normalize_line(no_tags) + "\n"


__all__ = ["html_to_plaintext", "html_to_plaintext_strict_fallback"]
