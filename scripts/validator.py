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


# Matches typical leftover placeholder text like [Author(s)], [YYYY/MM/DD],
# [Country], [Paper Title]. Excludes already-filled bracketed text by
# requiring the first character to be uppercase letter.
PLACEHOLDER_RE = re.compile(r"\[[A-Z][^\[\]]{1,60}\]")


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
    """Find unfilled [Placeholder] text in the rendered HTML body."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    found = PLACEHOLDER_RE.findall(text)
    # De-duplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for ph in found:
        if ph not in seen:
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
        # Don't block the build, but make the warning loud.
        warnings.append(
            f"{len(placeholders)} unfilled placeholder(s) found in the "
            f"newsletter body: {', '.join(placeholders[:6])}"
            + ("..." if len(placeholders) > 6 else "")
            + " -- these will appear literally in the sent email."
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
