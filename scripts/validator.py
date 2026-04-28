"""Validate the rendered HTML email — links, images, file size, placeholders."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scripts.config import GMAIL_CLIP_BYTES

log = logging.getLogger(__name__)


# Matches typical leftover placeholder text like [Author(s)],
# [YYYY/MM/DD], [Country], [Paper Title]. The pattern is intentionally
# broad -- it catches every unfilled placeholder in the template -- so
# legitimate scholarly citations like `[Fig. 1]` or `[J Med Chem 2023]`
# may be flagged too. Acceptable trade-off: validator output now says
# "Reminder: …review before sending", not "ERROR". False positives in
# real citations are easy for the editor to dismiss visually.
PLACEHOLDER_RE = re.compile(r"\[[A-Z][^\[\]]{1,60}\]")
# Lines that look like citations or editorial markers we DO know are
# legitimate -- exclude these from the warning.
_LEGIT_BRACKETED = re.compile(
    r"^\[(?:Sic|Ed\.?|Fig\.|Table\b|cf\.|et al\.|"
    r"\d+|"                    # numbered citation
    r"[A-Z][a-z]+ \d{4})"      # author-year [Smith 2023]
)


@dataclass(frozen=True)
class ValidationResult:
    size_bytes: int
    image_urls: tuple[str, ...]
    broken_images: tuple[str, ...]
    anchor_urls: tuple[str, ...]
    broken_anchors: tuple[str, ...]
    placeholders: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_url(url: str, timeout: float = 3.0) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:  # HEAD not allowed — try GET
            r = requests.get(url, timeout=timeout, stream=True)
        return 200 <= r.status_code < 400
    except Exception as e:
        log.debug("URL %s failed: %s", url, e)
        return False


def _scan_placeholders(html: str) -> tuple[str, ...]:
    """Find unfilled [Placeholder] text in the rendered HTML body.

    Recognised citation forms (`[Fig. 1]`, `[1]`, `[Smith 2023]`,
    `[Sic]`, etc.) are excluded so legitimate scholarly content
    doesn't trigger the warning.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    found = PLACEHOLDER_RE.findall(text)
    seen: set[str] = set()
    out: list[str] = []
    for ph in found:
        if _LEGIT_BRACKETED.match(ph):
            continue
        if ph in seen:
            continue
        seen.add(ph)
        out.append(ph)
    return tuple(out)


def validate(html: str, *, check_remote: bool = True) -> ValidationResult:
    soup = BeautifulSoup(html, "html.parser")
    img_urls = tuple(
        img["src"] for img in soup.find_all("img") if img.get("src")
    )
    anchor_urls = tuple(
        a["href"] for a in soup.find_all("a")
        if a.get("href", "").startswith(("http://", "https://"))
    )

    broken_images: list[str] = []
    broken_anchors: list[str] = []
    if check_remote:
        for url in img_urls:
            if url.startswith(("http://", "https://")):
                if not _check_url(url):
                    broken_images.append(url)
        for url in anchor_urls:
            if not _check_url(url):
                broken_anchors.append(url)

    size = len(html.encode("utf-8"))
    placeholders = _scan_placeholders(html)

    warnings: list[str] = []
    errors: list[str] = []

    if size > GMAIL_CLIP_BYTES:
        warnings.append(
            f"HTML is {size:,} bytes -- Gmail clips messages above "
            f"{GMAIL_CLIP_BYTES:,} bytes. Consider trimming images or text."
        )

    if placeholders:
        # Friendly nudge -- the build SUCCEEDED. We just want to warn the
        # editor that some bracket-style placeholders are still in the
        # text. Cap at 5 so the message is scannable; non-blocking.
        sample = ", ".join(placeholders[:5])
        more = (f" (+{len(placeholders) - 5} more)"
                if len(placeholders) > 5 else "")
        warnings.append(
            f"Reminder: {len(placeholders)} placeholder(s) still in the "
            f"newsletter -- {sample}{more}. The email was built; review "
            "before sending."
        )

    if broken_images:
        errors.append(
            f"{len(broken_images)} image URL(s) unreachable -- push assets "
            "before sending."
        )

    return ValidationResult(
        size_bytes=size,
        image_urls=img_urls,
        broken_images=tuple(broken_images),
        anchor_urls=anchor_urls,
        broken_anchors=tuple(broken_anchors),
        placeholders=placeholders,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def report(result: ValidationResult) -> str:
    lines = [
        f"Size: {result.size_bytes:,} bytes "
        f"({'OK' if result.size_bytes <= GMAIL_CLIP_BYTES else 'WARN - exceeds Gmail clip threshold'})",
        f"Images: {len(result.image_urls)} ({len(result.broken_images)} broken)",
        f"Links:  {len(result.anchor_urls)} ({len(result.broken_anchors)} broken)",
        f"Placeholders left unfilled: {len(result.placeholders)}",
    ]
    for w in result.warnings:
        lines.append(f"WARN: {w}")
    for e in result.errors:
        lines.append(f"ERROR: {e}")
    return "\n".join(lines)


__all__ = ["ValidationResult", "validate", "report"]
