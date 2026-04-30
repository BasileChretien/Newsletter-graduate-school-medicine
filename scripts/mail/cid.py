"""Inline-image (CID) attachment rewriter for the Outlook backend.

Background
----------
The default URL-based image flow ships a small HTML email with
`<img src="https://raw.githubusercontent.com/.../assets/issue-N/foo.jpg">`
and relies on the recipient's mail client fetching the image at
display time. That works for most clients, but a handful of corporate
filters (notably some hospital ones) quarantine `raw.githubusercontent.com`
specifically -- those recipients see broken-image icons.

The CID alternative ships the same email as a `multipart/related` MIME
message: the HTML references images by `<img src="cid:foo">`, and each
image is a real attached MIME part with a matching `Content-ID:` header.
Outlook desktop / Gmail web / Apple Mail all render CID images natively;
no external HTTP request fires; no domain-allowlist filter trips.

This module is the pure-logic bridge between an URL-rewritten HTML
(produced by the renderer + inliner) and the inline-attachment specs
the Outlook COM call needs. It is deliberately COM-free so it can be
exercised by `pytest` on every platform.

Public surface
--------------
* `InlineImage` -- frozen dataclass: (path, cid, original_url).
* `attach_inline_images(html, asset_dir, *, repo_url_prefix=...)` ->
  `(rewritten_html, tuple[InlineImage, ...])`.

A safe default
--------------
`<img>` tags whose `src` cannot be resolved to a real file under
`asset_dir` are LEFT UNTOUCHED. If the toolkit ever ships an image
whose URL doesn't follow the `<repo_url_prefix>/assets/issue-N/<file>`
convention (for example a future logo served from `images/`), the
URL keeps working as a remote reference -- recipients see the image
either way.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from scripts.html_utils import parse_html

log = logging.getLogger(__name__)


# CID values are quoted-printable strings that show up in `<img src=>`
# and in the `Content-ID:` MIME header. Outlook rejects characters it
# would have to encode (anything outside [a-z0-9._-]); we sanitize the
# basename to that subset and prefix it with `meridian-` so a CID
# never collides with a recipient's own `cid:` references in a quoted
# reply.
_CID_PREFIX = "meridian-"
# Default per-image attachment size cap. Round-12 architect MEDIUM N1:
# the bundle-12 default (500 KB) was too aggressive -- typical
# institutional photos run 200-800 KB, so a non-trivial fraction of
# issues silently fell back to URL mode for SOME images while
# attaching others, producing mixed-mode emails (some inline, some
# external -- inconsistent rendering for recipients on filtered
# networks). 2 MB is generous enough to cover normal institutional
# imagery while still rejecting accidental-multimegapixel-paste
# pathologies. Surfaced as `--cid-max-image-mb` on the CLI for
# editors who need to tune it.
DEFAULT_MAX_IMAGE_BYTES = 2_000_000
# RFC 2822 msg-id shape: `local-part@domain`. Older Outlook builds
# (2013, some 2016 LTSC) don't auto-wrap PR_ATTACH_CONTENT_ID values
# in `<...>` when serializing MIME. Suffixing with `@meridian.local`
# means the value already looks like a valid `Content-ID:` regardless
# of whether the angle brackets get added (round-12 deliverability M2).
_CID_DOMAIN = "meridian.local"
_CID_SAFE_RE = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class InlineImage:
    """Spec for one image to be attached as an inline MIME part.

    `path`         -- local file the Outlook backend will pass to
                       `mail.Attachments.Add()`.
    `cid`          -- value used in both `<img src="cid:...">` and the
                       attachment's `Content-ID:` MAPI property. No
                       angle brackets here; the COM layer adds them.
    `original_url` -- the `https://...` URL that was rewritten. Kept
                       for diagnostics (logs / dropped-image lists).
    """

    path: Path
    cid: str
    original_url: str


def _make_cid(basename: str, index: int, *,
              issue_tag: str = "") -> str:
    """Build a deterministic, RFC-2392-safe Content-ID for `basename`.

    Determinism matters: if the editor regenerates the same issue
    twice (because they fixed a typo and re-sent), the CID values
    stay identical. This makes it possible -- in a future version --
    to compare two builds and check that "only X changed" without
    being misled by a fresh random suffix.

    The `index` disambiguates files that happen to share a slug
    after the safe-charset filter (e.g. an editor uploads
    `lab.JPG` and `lab.jpg` in the same issue).

    `issue_tag` discriminates CIDs across different issues so that a
    forwarded thread containing two issues doesn't collapse two
    different images into one (round-12 architect HIGH 1). The MUA
    deduplicates by `Content-ID`; identical CIDs across issues mean
    the second image silently shadows the first when both messages
    sit in the same conversation. Pass e.g. `asset_dir.name`
    (`"issue-3"`) so cross-issue CIDs differ.

    Output shape (RFC 2822 msg-id):
      `meridian-{issue_tag-}{index}-{safe}@meridian.local`
    Example: `meridian-issue-3-01-photo1.jpg@meridian.local`.
    """
    safe = _CID_SAFE_RE.sub("-", basename.lower()).strip("-")
    if not safe:
        safe = f"image-{index}"
    issue_part = ""
    if issue_tag:
        issue_safe = _CID_SAFE_RE.sub("-", issue_tag.lower()).strip("-")
        if issue_safe:
            issue_part = f"{issue_safe}-"
    return f"{_CID_PREFIX}{issue_part}{index:02d}-{safe}@{_CID_DOMAIN}"


def _confined(candidate: Path, root: Path) -> Path | None:
    """Return `candidate.resolve()` iff it stays inside `root.resolve()`.

    Round-11 phase-1 security HIGH 1+2: the previous version of
    `_resolve_local_path` `joinpath`d every URL path segment after the
    `assets` / `images` marker, including `..` segments. A crafted
    DOCX containing
    `<img src="https://raw.githubusercontent.com/.../assets/issue-1/../../etc/passwd">`
    would resolve to a path outside the project root; the only guard
    was `is_file()`, which DOES return True for genuinely-existing
    files anywhere on disk. CID mode would then attach
    `/etc/passwd` to the outgoing email.

    Defence: `Path.resolve()` collapses `..` lexically; `is_relative_to`
    rejects anything that ended up outside `root`. Symlinks pointing
    outside the tree are also caught because `resolve()` follows them.
    """
    try:
        resolved = candidate.resolve(strict=False)
        root_resolved = root.resolve(strict=False)
    except (OSError, ValueError) as e:
        log.debug("Path resolution failed for %s: %s", candidate, e)
        return None
    try:
        if not resolved.is_relative_to(root_resolved):
            log.warning(
                "CID skip: %s resolves to %s, which is outside %s. "
                "Possible crafted-DOCX path-traversal attempt.",
                candidate, resolved, root_resolved,
            )
            return None
    except ValueError:
        # Different drives on Windows. Definitely outside the root.
        return None
    if not resolved.is_file():
        return None
    return resolved


def _resolve_local_path(src: str, asset_dir: Path,
                        repo_url_prefix: str) -> Path | None:
    """Map an `<img src=>` URL to a local file under `asset_dir`.

    Recognised shapes (matched against `repo_url_prefix`):
      * `<prefix>/<user>/<repo>/<branch>/assets/issue-<N>/<file>`
      * `<prefix>/<user>/<repo>/<branch>/images/<file>`

    Anything else returns `None` so the caller can leave the URL
    untouched. Robust to whether `repo_url_prefix` includes a trailing
    slash and whether it stops at the host or extends to the branch.

    Path-traversal hardening: every candidate path is run through
    `_confined` to ensure it stays inside the project's `assets/` or
    `images/` directory. URL segments equal to `..` or containing a
    null byte are also explicitly rejected before the `joinpath` to
    catch the case of a future `urllib.parse.unquote()` step
    (currently absent) reintroducing traversal.
    """
    if not src.startswith(repo_url_prefix):
        return None
    # Walk the URL's path segments. We don't care what comes BEFORE
    # the `assets` / `images` marker (it might be `<user>/<repo>/<branch>/`
    # or empty depending on how aggressively the caller pre-stripped);
    # we only care that one of those markers is a real path segment
    # (not a substring of an unrelated segment like `meta-assets`).
    parsed = urlparse(src)
    parts = [p for p in parsed.path.split("/") if p]

    # Reject any segment that's a parent-dir reference or contains a
    # null byte. `urlparse` doesn't decode percent-encoded bytes, so
    # `%2E%2E` arrives as the opaque string `%2E%2E` (which is fine --
    # `joinpath("%2E%2E")` makes a literal directory of that name, which
    # then fails `is_file()`). But a URL with literal `..` segments
    # would traverse if we let it through. Round-11 security M1.
    def _is_safe_segment(seg: str) -> bool:
        return seg not in ("..",) and "\x00" not in seg

    if not all(_is_safe_segment(p) for p in parts):
        log.warning(
            "CID skip: %s contains a parent-dir or null-byte segment.",
            src,
        )
        return None

    # `assets/issue-N/<file>`: file lives at `asset_dir.parent / issue-N / file`.
    # Confine to `asset_dir.parent.resolve()` so `joinpath` can't escape.
    if "assets" in parts:
        idx = parts.index("assets")
        rel_parts = parts[idx + 1:]
        if not rel_parts:
            return None
        root = asset_dir.parent
        candidate = root.joinpath(*rel_parts)
        return _confined(candidate, root)
    # `images/<file>`: file lives at the project's permanent brand-asset
    # directory, sibling to `assets/`.
    if "images" in parts:
        idx = parts.index("images")
        rel_parts = parts[idx + 1:]
        if not rel_parts:
            return None
        root = asset_dir.parent.parent / "images"
        candidate = root.joinpath(*rel_parts)
        return _confined(candidate, root)
    return None


def attach_inline_images(
    html: str,
    asset_dir: Path,
    *,
    repo_url_prefix: str = "https://raw.githubusercontent.com/",
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> tuple[str, tuple[InlineImage, ...]]:
    """Rewrite `<img>` tags in `html` to use CID references.

    For every `<img src="<repo_url_prefix>...">` whose URL resolves to
    a real file on disk under `asset_dir` (or its sibling `images/`
    directory), this function:

      1. Computes a deterministic CID via `_make_cid` (issue-discriminated
         via `asset_dir.name` so a forwarded thread spanning issue 5 +
         issue 6 doesn't collapse the two `photo1.jpg` files into one).
      2. Replaces `src` with `src="cid:<that-cid>"`.
      3. Records the local path + CID + original URL in the returned
         tuple so the caller (Outlook backend) can attach the file.

    `<img>` tags whose `src` cannot be resolved locally are left
    UNTOUCHED -- including their original URL. This means a CID
    build with a few unresolvable images degrades gracefully: those
    images load over HTTP exactly as they would in URL mode.

    `max_image_bytes` (default 500 KB) caps the per-image attachment
    size. Files over the cap are LEFT AS URLs rather than attached --
    a 4 MB hospital exterior shot would otherwise bloat every
    forwarded copy of the message (a 50-recipient × 5-forward chain
    sends ~25 MB of duplicated photo across the corporate network).
    Round-12 deliverability MEDIUM 1 / HIGH 2.

    Returns `(rewritten_html, inline_images_tuple)`. The HTML is
    structurally identical to the input apart from rewritten `src`
    attributes; the same BeautifulSoup parser used everywhere else in
    the toolkit handles it.
    """
    soup = parse_html(html)
    inline: list[InlineImage] = []
    seen: dict[str, str] = {}  # local-path -> already-assigned CID
    skipped_too_large = 0
    skipped_unresolvable = 0
    rewritten_count = 0
    # Issue tag for cross-issue CID disambiguation. `asset_dir.name`
    # is typically `"issue-N"` -- exactly what we want.
    issue_tag = asset_dir.name

    for idx, img in enumerate(soup.find_all("img"), start=1):
        src = img.get("src", "")
        if not src or src.startswith("cid:"):
            # Empty or already-CID -- skip silently.
            continue
        local = _resolve_local_path(src, asset_dir, repo_url_prefix)
        if local is None:
            skipped_unresolvable += 1
            log.debug("CID skip: src=%r has no local match under %s",
                      src, asset_dir)
            continue
        # Per-image size cap -- leave large files as URLs.
        try:
            size = local.stat().st_size
        except OSError as e:
            log.warning("CID skip: stat(%s) failed (%s); leaving as URL.",
                        local, e)
            continue
        if size > max_image_bytes:
            skipped_too_large += 1
            log.warning(
                "CID skip: %s is %d bytes (> %d cap). Leaving as URL "
                "to avoid bloating forwarded message size.",
                local, size, max_image_bytes,
            )
            continue
        # If the same local file is referenced twice in the HTML
        # (rare, but possible -- e.g. a logo in masthead AND footer),
        # reuse the same CID so we attach the file exactly once.
        key = str(local)
        if key in seen:
            cid = seen[key]
        else:
            cid = _make_cid(local.name, idx, issue_tag=issue_tag)
            seen[key] = cid
            inline.append(InlineImage(
                path=local, cid=cid, original_url=src,
            ))
        img["src"] = f"cid:{cid}"
        rewritten_count += 1

    rewritten = str(soup)
    log.info(
        "CID rewrite: %d <img> rewritten (%d unique attachments), "
        "%d unresolvable URLs left external, %d files over %d-byte cap.",
        rewritten_count, len(inline),
        skipped_unresolvable, skipped_too_large, max_image_bytes,
    )
    return rewritten, tuple(inline)


__all__ = ["InlineImage", "attach_inline_images"]
