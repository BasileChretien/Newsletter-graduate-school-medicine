"""Validate the rendered HTML email — links, images, file size."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scripts.config import GMAIL_CLIP_BYTES

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    size_bytes: int
    image_urls: tuple[str, ...]
    broken_images: tuple[str, ...]
    anchor_urls: tuple[str, ...]
    broken_anchors: tuple[str, ...]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
    result = ValidationResult(
        size_bytes=size,
        image_urls=img_urls,
        broken_images=tuple(broken_images),
        anchor_urls=anchor_urls,
        broken_anchors=tuple(broken_anchors),
    )

    if size > GMAIL_CLIP_BYTES:
        result.warnings.append(
            f"HTML is {size:,} bytes — Gmail clips messages above "
            f"{GMAIL_CLIP_BYTES:,} bytes. Consider trimming images or text."
        )

    if broken_images:
        result.errors.append(
            f"{len(broken_images)} image URL(s) unreachable — push assets "
            "before sending."
        )

    return result


def report(result: ValidationResult) -> str:
    lines = [
        f"Size: {result.size_bytes:,} bytes "
        f"({'OK' if result.size_bytes <= GMAIL_CLIP_BYTES else 'WARN — exceeds Gmail clip threshold'})",
        f"Images: {len(result.image_urls)} ({len(result.broken_images)} broken)",
        f"Links:  {len(result.anchor_urls)} ({len(result.broken_anchors)} broken)",
    ]
    for w in result.warnings:
        lines.append(f"WARN: {w}")
    for e in result.errors:
        lines.append(f"ERROR: {e}")
    return "\n".join(lines)


__all__ = ["ValidationResult", "validate", "report"]
