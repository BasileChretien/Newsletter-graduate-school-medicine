"""Validate the rendered HTML email — links, images, file size, placeholders."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import requests

from scripts.config import GMAIL_CLIP_BYTES
from scripts.html_utils import parse_html, remove_hidden_elements
from scripts.text_utils import normalize_for_match

log = logging.getLogger(__name__)

# Early-warn threshold -- 80 KB leaves ~22 KB headroom before Gmail clips.
_GMAIL_EARLY_WARN_BYTES = 80_000
_HEAD_WORKERS = 8
_HEAD_TIMEOUT = 3.0


# Matches typical leftover placeholder text like [Author(s)],
# [YYYY/MM/DD], [Country], [Paper Title]. The pattern is intentionally
# broad -- it catches every unfilled placeholder in the template -- so
# legitimate scholarly citations like `[Fig. 1]` or `[J Med Chem 2023]`
# may be flagged too. Acceptable trade-off: validator output now says
# "Reminder: …review before sending", not "ERROR". False positives in
# real citations are easy for the editor to dismiss visually.
PLACEHOLDER_RE = re.compile(r"\[[A-Z][^\[\]]{1,60}\]")
# Tokens that mean the masthead's `VOL. XX | ISSUE NO. XX | MONTH YEAR`
# placeholders weren't filled in. If any of these survive into the
# rendered HTML, the recipient's inbox will preview a "broken send"
# subject like "MERIDIAN -- VOL. XX | ISSUE NO. XX | MONTH YEAR".
_UNFILLED_MASTHEAD_TOKENS = (
    "VOL. XX",
    "ISSUE NO. XX",
    "MONTH YEAR",
)


# Lines that look like citations or editorial markers we DO know are
# legitimate -- exclude these from the warning. Anchored with `\]$` so
# the pattern doesn't false-match arbitrary trailing junk like
# `[Smith 2023xyz extra]`.
_LEGIT_BRACKETED = re.compile(
    r"^\[(?:"
    r"Sic|Ed\.?|Fig\.[^\[\]]*|Table[^\[\]]*|cf\.[^\[\]]*|"
    r"\d+|"                                          # [1] [42]
    r"[A-Z][a-z]+ \d{4}|"                            # [Smith 2023]
    r"[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*)+\s+\d{4}|"  # [J Med Chem 2023]
    r"[^\[\]]+et al\."                               # [Smith et al.]
    r")\]$"
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


def _check_url(url: str, timeout: float = _HEAD_TIMEOUT) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:  # HEAD not allowed — try GET
            with requests.get(url, timeout=timeout, stream=True) as r:
                return 200 <= r.status_code < 400
        return 200 <= r.status_code < 400
    except (requests.RequestException, OSError) as e:
        log.debug("URL %s failed: %s", url, e)
        return False


def _check_urls_parallel(urls: tuple[str, ...]) -> list[str]:
    """Return the subset of `urls` that are not reachable.

    Runs HEAD checks across a thread pool (max _HEAD_WORKERS). For 30
    images this completes in ~3-5 seconds instead of ~90 seconds serial.
    """
    if not urls:
        return []
    broken: list[str] = []
    with ThreadPoolExecutor(max_workers=_HEAD_WORKERS) as pool:
        future_to_url = {pool.submit(_check_url, u): u for u in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                ok = future.result()
            except (requests.RequestException, OSError) as e:
                log.debug("URL %s failed: %s", url, e)
                ok = False
            except Exception as exc:  # noqa: BLE001 -- log the unexpected
                log.warning("URL check future raised unexpectedly: %s", exc)
                ok = False
            if not ok:
                broken.append(url)
    return broken


def _scan_placeholders(html: str) -> tuple[str, ...]:
    """Find unfilled [Placeholder] text in the rendered HTML body.

    Recognised citation forms (`[Fig. 1]`, `[1]`, `[Smith 2023]`,
    `[Sic]`, etc.) are excluded so legitimate scholarly content
    doesn't trigger the warning.
    """
    soup = parse_html(html)
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
    # Drop hidden elements before scanning images/anchors. Round-10
    # security LOW 5: a malicious DOCX hyperlink that the renderer
    # leaves wrapped in `[hidden]` would otherwise be HEAD-checked
    # for reachability AND end up in the audit trail's anchor_urls
    # tuple even though the recipient can't see it.
    soup = parse_html(html)
    remove_hidden_elements(soup)
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
        http_imgs = tuple(u for u in img_urls
                          if u.startswith(("http://", "https://")))
        broken_images = _check_urls_parallel(http_imgs)
        broken_anchors = _check_urls_parallel(anchor_urls)

    size = len(html.encode("utf-8"))
    placeholders = _scan_placeholders(html)

    warnings: list[str] = []
    errors: list[str] = []

    if size > GMAIL_CLIP_BYTES:
        warnings.append(
            "Heads up: this email is quite long. Gmail may show a "
            "'View entire message' link to recipients. Consider "
            "trimming a section or shrinking images."
        )
    elif size > _GMAIL_EARLY_WARN_BYTES:
        warnings.append(
            "Heads up: this email is getting long. If it grows much "
            "more, Gmail may truncate it for recipients."
        )

    if placeholders:
        # Friendly nudge -- the build SUCCEEDED. Reframe as "brackets
        # you may want to fill in" rather than "placeholder count
        # remaining" so editors testing the toolkit don't feel scolded.
        sample = ", ".join(placeholders[:5])
        more = (f" (+{len(placeholders) - 5} more)"
                if len(placeholders) > 5 else "")
        fresh_hint = (
            " -- this is normal for an unfilled template; fill the "
            "brackets in Word and re-run"
            if len(placeholders) >= 20 else ""
        )
        warnings.append(
            f"Reminder: there are still {len(placeholders)} brackets "
            f"like {sample}{more} you may want to fill in"
            f"{fresh_hint}. The email was built; review before sending."
        )

    if broken_images:
        # WARN, not ERROR -- a flaky HEAD check shouldn't abort the
        # editor's pipeline. The publish step pushes assets anyway; if
        # the URLs really are broken at send time, a recipient sees a
        # broken image but the editor has already sent.
        warnings.append(
            f"{len(broken_images)} photo(s) couldn't be reached on the "
            "web yet. They may still be uploading -- try previewing in "
            "a minute. If broken images persist, run 'publish-images'."
        )

    # Hard-blocker: the masthead "VOL. XX | ISSUE NO. XX | MONTH YEAR"
    # placeholders MUST be filled before sending. Recipients see the
    # subject line / inbox preview built from this -- shipping with
    # `VOL. XX` looks like a broken send and triggers spam-filter
    # heuristics. Not just a reminder -- abort the build.
    #
    # We check the *visible-to-recipients* text -- not raw HTML -- so:
    #   * the explanatory `<!-- ... VOL. XX ... -->` comment in the
    #     template doesn't false-positive (BeautifulSoup's get_text
    #     drops comments).
    #   * elements the recipient never sees (display:none / hidden /
    #     mso-hide:all preheader fallbacks) don't false-positive
    #     either -- we drop them BEFORE pulling text out.
    #
    # Normalization (`normalize_for_match`) is shared with
    # `sanitize_subject` in text_utils, so subject-line and
    # masthead-token defenses against NBSP / fullwidth substitutions
    # stay in lockstep.
    visible_soup = parse_html(html)
    remove_hidden_elements(visible_soup)
    visible_text = visible_soup.get_text(" ", strip=True)
    normalized_text = normalize_for_match(visible_text)
    leaked = [
        tok for tok in _UNFILLED_MASTHEAD_TOKENS if tok in normalized_text
    ]
    if leaked:
        errors.append(
            "The masthead's issue line still contains unfilled "
            f"placeholder text ({', '.join(leaked)}). Please open your "
            "Word file and replace it with real values "
            "(e.g. 'VOL. 12 | ISSUE NO. 3 | MARCH 2026') before sending. "
            "Recipients see this in their inbox preview."
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
