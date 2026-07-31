"""HTML -> plaintext conversion for the multipart/alternative body.

Most corporate spam filters (Mimecast, Proofpoint, Microsoft Defender,
Barracuda) score HTML-only mail higher than `multipart/alternative`,
and they also score the *ratio* of plaintext to HTML -- a one-line
plaintext alongside 33 KB of HTML still triggers "HTML-heavy" rules.
So we don't just produce *some* plaintext; we produce **structurally
preserved** plaintext: heading markers, bullet glyphs, link URLs.

Conversion rules:

* Block elements (`<p>`, `<h1..h6>`, `<tr>`, `<li>`, `<br>`, `<div>`)
  produce line breaks. The output is CRLF-terminated (RFC 5322 §2.3
  mandates CRLF for mail bodies; bundle 28's bare-LF output relied
  on undocumented Outlook COM behaviour and could trip strict MIME
  validators on Send-As / forwarded paths).
* `<h1>` / `<h2>` -> `=== HEADING ===` (eye-catching for plaintext
  readers AND clearly heading-shaped to spam-filter heuristics that
  score unstructured plaintext lower). Heading rewriting runs BEFORE
  link expansion so a heading that contains an `<a>` doesn't end up
  with a URL leak inside the marker (round-10 python-reviewer HIGH).
* `<h3>` / `<h4>` / `<h5>` / `<h6>` -> `--- subheading ---`
* `<li>` -> `<bullet>` glyph prefix.
* Hyperlinks: `<a href="X">label</a>` -> `label (X)` so the URL is
  visible to plaintext readers. Scheme allowlist
  (`http://` / `https://` / `mailto:`) is matched case-INsensitively
  so legitimate `HTTPS://...` survives (round-10 security MEDIUM 3).
* Whitespace runs collapse to single space (preserves line structure
  by working line-by-line).
* All HTML comments are stripped.
* Hidden elements (display:none / visibility:hidden / hidden attribute)
  drop entirely -- recipient invisibility carries through to plaintext.
* `<thead>` / `<tbody>` / `<tfoot>` are NOT in `_BLOCK_TAGS` -- they
  are structural grouping wrappers, not visual blocks, and adding
  newlines around them duplicated the line breaks the inner `<tr>`
  already emits (round-10 deliverability HIGH 2). Dropping them
  recovers ~30% of plaintext bytes that had been wasted on whitespace.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

from scripts.html_utils import parse_html, remove_hidden_elements
from scripts.text_utils import SAFE_URL_SCHEMES, is_safe_url_scheme


_BLOCK_TAGS: frozenset[str] = frozenset({
    "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "hr", "section", "article", "header", "footer",
    # NOTE: `thead` / `tbody` / `tfoot` are intentionally excluded.
    # The inner `<tr>` already emits newlines; wrapping the group too
    # produces duplicate blank lines that bloat the plaintext part.
})

_DROP_TAGS: frozenset[str] = frozenset({
    "script", "style", "head", "meta", "link",
})

# The scheme allowlist now lives in `scripts.text_utils` so the HTML
# part and the plaintext part cannot diverge. They did: this module
# stripped `file://` while the HTML sibling shipped it, which meant a
# plaintext client, an archive review and a DLP scan all saw a clean
# message while the rendered one carried the hostile target.
_SAFE_URL_SCHEMES = SAFE_URL_SCHEMES

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

# Block-level HTML tags whose closing/breaking emits a hard break --
# used by the strict-fallback regex stripper to preserve some
# structure even when the BS4 path raises (round-10 deliverability M1).
_FALLBACK_BLOCK_BREAK_RE = re.compile(
    r"</\s*(?:p|div|li|tr|h[1-6]|blockquote|pre|section|article|"
    r"header|footer|td|th)\s*>|<\s*br\s*/?\s*>",
    flags=re.IGNORECASE,
)


def _normalize_line(line: str) -> str:
    r"""Collapse all in-line whitespace runs to a single ASCII space.

    Includes NBSP (U+00A0) -- Word's auto-format substitutes NBSP for
    ASCII space when text is pasted, and we want the plaintext output
    to read with normal spacing. Use the explicit `\u00a0` escape
    rather than a literal NBSP byte, so a future editor reformatting
    this line can't silently strip it (round-9 python-reviewer
    MEDIUM).
    """
    return re.sub(r"[ \t\u00a0]+", " ", line).strip()


def _to_crlf(s: str) -> str:
    """Normalize all newlines to CRLF.

    RFC 5322 §2.3 mandates CRLF in mail bodies. Bundle 28 relied on
    Outlook COM converting bare LF on serialization, which is true
    for HTMLBody auto-generation but undocumented for an explicitly
    set `Body`. On Send-As / forwarded paths via Exchange Online,
    bare-LF text parts can be flagged by strict MIME validators.
    Round-10 deliverability HIGH 1.
    """
    # Two-step: first collapse pre-existing CRLF to LF so we don't
    # double-convert, then promote LF to CRLF.
    return s.replace("\r\n", "\n").replace("\n", "\r\n")


def _is_safe_scheme(href: str) -> bool:
    """Thin delegate to `scripts.text_utils.is_safe_url_scheme`.

    Kept as a name because this module's tests reference it. The shared
    implementation is strictly stronger than the one that lived here: it
    normalizes (NFKC), strips invisibles and control characters, and
    then compares, so `java<ZWSP>script:` and `javascript:` are
    rejected where a bare `.lower().startswith()` accepted them.
    """
    return is_safe_url_scheme(href)


def _rewrite_headings(soup: BeautifulSoup) -> None:
    """Wrap headings in marker prefixes/suffixes.

    Runs BEFORE link rewriting so a heading like
    `<h2><a href="x">Link</a></h2>` produces `=== LINK ===`, not the
    bundle-28 leak `=== LINK (HTTPS://X.COM) ===`. The `<a>` is then
    rewritten by `_rewrite_anchors`, but at that point the heading is
    already a single NavigableString -- the link rewriter only matches
    surviving `<a>` tags, which there are none of inside the heading.

    Major (`h1`/`h2`) headings get uppercased; minor (`h3..h6`) keep
    their original case. Both branches (`.string` simple vs nested-
    tag) apply the same uppercasing rule (round-10 deliverability M2).
    """
    for h in soup.find_all(["h1", "h2"]):
        label = h.get_text(" ", strip=True).upper()
        h.clear()
        h.append(NavigableString(
            f"{_H_MAJOR_PREFIX}{label}{_H_MAJOR_SUFFIX}"
        ))
    for h in soup.find_all(["h3", "h4", "h5", "h6"]):
        label = h.get_text(" ", strip=True)
        h.clear()
        h.append(NavigableString(
            f"{_H_MINOR_PREFIX}{label}{_H_MINOR_SUFFIX}"
        ))


def _rewrite_anchors(soup: BeautifulSoup) -> None:
    """Replace `<a href="X">label</a>` with `label (X)`.

    Drops unsafe schemes (case-insensitively); preserves the visible
    label only when the href is unsafe or empty.
    """
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        label = a.get_text(" ", strip=True)
        if href and _is_safe_scheme(href):
            if label and label != href:
                a.replace_with(f"{label} ({href})")
            else:
                a.replace_with(href)
        else:
            # Unsafe scheme or empty href -- preserve the visible label
            # only. Never expose `javascript:` / `data:` / `file:` /
            # `tel:` / `vbscript:` / etc.
            a.replace_with(label)


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    """Collapse runs of >1 blank line into exactly one blank line."""
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
    return out


def html_to_plaintext(html: str) -> str:
    """Convert an HTML string to a readable, spam-friendly plaintext.

    Output is suitable for `multipart/alternative` text part: visible
    URLs after link text, heading / subhead markers, bullet glyphs,
    line-broken on block boundaries, CRLF-terminated, no HTML
    artefacts.

    Never raises in practice -- malformed HTML is handled gracefully
    by BeautifulSoup. The Outlook backend still wraps the call in a
    try/except as belt-and-braces; on exception the strict-fallback
    below produces a less-pretty but still structurally-broken-up
    plaintext to keep the MIME message multipart/alternative.
    """
    soup = parse_html(html)

    # Drop tags whose text we never want in the plaintext (script
    # body, CSS rules, head metadata).
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Drop hidden elements -- recipient-invisible -> plaintext-invisible.
    # Shared helper so this list stays in lockstep with the validator's
    # masthead-guard (round-9 code-review HIGH).
    remove_hidden_elements(soup)

    # Order matters: rewrite headings BEFORE links. A heading that
    # contains an `<a>` would otherwise leak the URL into the marker
    # ("=== LINK (HTTPS://X.COM) ===" -- round-10 python-reviewer HIGH).
    _rewrite_headings(soup)
    _rewrite_anchors(soup)

    # Prefix list items with a bullet glyph.
    for li in soup.find_all("li"):
        li.insert(0, NavigableString(_BULLET))

    # Insert newline markers around block-level tags before pulling text.
    for tag in soup.find_all(True):
        if tag.name in _BLOCK_TAGS:
            tag.insert_before(NavigableString("\n"))
            tag.insert_after(NavigableString("\n"))

    raw = soup.get_text(separator="")

    # Collapse whitespace within each line, then collapse runs of >1
    # blank lines into exactly one blank line.
    lines = _collapse_blank_runs(
        [_normalize_line(ln) for ln in raw.splitlines()]
    )
    text = "\n".join(lines).strip() + "\n"
    return _to_crlf(text)


def html_to_plaintext_strict_fallback(html: str) -> str:
    """Last-resort plaintext conversion used when `html_to_plaintext`
    raises (which shouldn't happen, but Outlook drafts are a bad
    place to discover an unhandled exception).

    Round-10 deliverability M1: bundle 28 collapsed everything to a
    single line, which several spam filters (SpamAssassin LONG_LINE,
    Mimecast structural-quality) score as machine-generated. We now
    preserve block boundaries by inserting `\\n` at every closing
    block-tag / `<br>` BEFORE stripping the rest, then run the same
    blank-run collapse + CRLF normalization as the main path. The
    result isn't pretty (no headings / bullets / URL surfacing) but
    it does ship structured paragraphs.
    """
    # Insert hard breaks at block boundaries BEFORE stripping tags.
    with_breaks = _FALLBACK_BLOCK_BREAK_RE.sub("\n", html)
    no_tags = re.sub(r"<[^>]+>", "", with_breaks)
    lines = _collapse_blank_runs(
        [_normalize_line(ln) for ln in no_tags.splitlines()]
    )
    text = "\n".join(lines).strip() + "\n"
    return _to_crlf(text)


__all__ = ["html_to_plaintext", "html_to_plaintext_strict_fallback"]
