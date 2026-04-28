"""HTML -> plaintext conversion for the multipart/alternative body.

Most corporate spam filters (Mimecast, Proofpoint, Microsoft Defender,
Barracuda) score HTML-only mail higher than `multipart/alternative`.
The MIME type also matters for screen readers and for clients that
don't render HTML at all (a small but non-zero share, e.g. some
hospital terminals).

Conversion rules:

* Block elements (`<p>`, `<h1..h6>`, `<tr>`, `<li>`, `<br>`, `<div>`)
  produce line breaks. Outlook's COM `Body` setter will normalize
  `\\n` to `\\r\\n` when serializing the MIME, so we don't need to.
* Hyperlinks become `link text (https://example.com/)` so the URL is
  visible to plaintext readers.
* Whitespace runs collapse to single space (preserves line structure
  by working line-by-line).
* All HTML comments are stripped.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag


_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "hr", "section", "article", "header", "footer",
    "thead", "tbody", "tfoot",
})

_DROP_TAGS: frozenset[str] = frozenset({"script", "style", "head", "meta", "link"})


def html_to_plaintext(html: str) -> str:
    """Convert an HTML string to a readable plaintext alternative.

    Output is suitable for `multipart/alternative` text part: visible
    URLs after link text, line-broken on block boundaries, no HTML
    artefacts.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Drop tags whose text we never want in the plaintext (script
    # body, CSS rules, head metadata).
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Drop hidden elements -- they're not visible to recipients in
    # the HTML body, so they shouldn't be in the plaintext either.
    for hidden in soup.select(
        "[style*='display:none'], [style*='display: none'], "
        "[style*='visibility:hidden'], [style*='visibility: hidden'], "
        "[hidden]"
    ):
        hidden.decompose()

    # Replace <a href="X">label</a> with "label (X)" so plaintext
    # readers can copy / click the URL.
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        label = a.get_text(" ", strip=True)
        if href and href.startswith(("http://", "https://", "mailto:")):
            if label and label != href:
                a.replace_with(f"{label} ({href})")
            else:
                a.replace_with(href)
        else:
            a.replace_with(label)

    # Insert newline markers around block-level tags before pulling text.
    for tag in soup.find_all(True):
        if tag.name in _BLOCK_TAGS:
            tag.insert_before(NavigableString("\n"))
            tag.insert_after(NavigableString("\n"))

    raw = soup.get_text(separator="")

    # Collapse whitespace within each line, then collapse runs of >2
    # blank lines into exactly one blank line.
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in raw.splitlines()]
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


__all__ = ["html_to_plaintext"]
