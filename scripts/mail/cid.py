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


def _make_cid(basename: str, index: int) -> str:
    """Build a deterministic, RFC-2392-safe Content-ID for `basename`.

    Determinism matters: if the editor regenerates the same issue
    twice (because they fixed a typo and re-sent), the CID values
    stay identical. This makes it possible -- in a future version --
    to compare two builds and check that "only X changed" without
    being misled by a fresh random suffix.

    The `index` disambiguates files that happen to share a slug
    after the safe-charset filter (e.g. an editor uploads
    `lab.JPG` and `lab.jpg` in the same issue).
    """
    safe = _CID_SAFE_RE.sub("-", basename.lower()).strip("-")
    if not safe:
        safe = f"image-{index}"
    return f"{_CID_PREFIX}{index:02d}-{safe}"


def _resolve_local_path(src: str, asset_dir: Path,
                        repo_url_prefix: str) -> Path | None:
    """Map an `<img src=>` URL to a local file under `asset_dir`.

    Recognised shapes (matched against `repo_url_prefix`):
      * `<prefix>/<user>/<repo>/<branch>/assets/issue-<N>/<file>`
      * `<prefix>/<user>/<repo>/<branch>/images/<file>`

    Anything else returns `None` so the caller can leave the URL
    untouched. Robust to whether `repo_url_prefix` includes a trailing
    slash and whether it stops at the host or extends to the branch.
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
    # `assets/issue-N/<file>`: file lives at `asset_dir.parent / issue-N / file`.
    if "assets" in parts:
        idx = parts.index("assets")
        rel_parts = parts[idx + 1:]
        if not rel_parts:
            return None
        candidate = asset_dir.parent.joinpath(*rel_parts)
        return candidate if candidate.is_file() else None
    # `images/<file>`: file lives at the project's permanent brand-asset
    # directory, sibling to `assets/`.
    if "images" in parts:
        idx = parts.index("images")
        rel_parts = parts[idx + 1:]
        if not rel_parts:
            return None
        candidate = asset_dir.parent.parent.joinpath("images", *rel_parts)
        return candidate if candidate.is_file() else None
    return None


def attach_inline_images(
    html: str,
    asset_dir: Path,
    *,
    repo_url_prefix: str = "https://raw.githubusercontent.com/",
) -> tuple[str, tuple[InlineImage, ...]]:
    """Rewrite `<img>` tags in `html` to use CID references.

    For every `<img src="<repo_url_prefix>...">` whose URL resolves to
    a real file on disk under `asset_dir` (or its sibling `images/`
    directory), this function:

      1. Computes a deterministic CID via `_make_cid`.
      2. Replaces `src` with `src="cid:<that-cid>"`.
      3. Records the local path + CID + original URL in the returned
         tuple so the caller (Outlook backend) can attach the file.

    `<img>` tags whose `src` cannot be resolved locally are left
    UNTOUCHED -- including their original URL. This means a CID
    build with a few unresolvable images degrades gracefully: those
    images load over HTTP exactly as they would in URL mode.

    Returns `(rewritten_html, inline_images_tuple)`. The HTML is
    structurally identical to the input apart from rewritten `src`
    attributes; the same BeautifulSoup parser used everywhere else in
    the toolkit handles it.
    """
    soup = parse_html(html)
    inline: list[InlineImage] = []
    seen: dict[str, str] = {}  # local-path -> already-assigned CID

    for idx, img in enumerate(soup.find_all("img"), start=1):
        src = img.get("src", "")
        if not src or src.startswith("cid:"):
            # Empty or already-CID -- skip.
            continue
        local = _resolve_local_path(src, asset_dir, repo_url_prefix)
        if local is None:
            log.debug("CID skip: src=%r has no local match under %s",
                      src, asset_dir)
            continue
        # If the same local file is referenced twice in the HTML
        # (rare, but possible -- e.g. a logo in masthead AND footer),
        # reuse the same CID so we attach the file exactly once.
        key = str(local)
        if key in seen:
            cid = seen[key]
        else:
            cid = _make_cid(local.name, idx)
            seen[key] = cid
            inline.append(InlineImage(
                path=local, cid=cid, original_url=src,
            ))
        img["src"] = f"cid:{cid}"

    rewritten = str(soup)
    log.info("CID rewrite: %d image(s) attached, %d URL(s) left external.",
             len(inline), sum(1 for _ in soup.find_all("img"))
             - len(seen))
    return rewritten, tuple(inline)


__all__ = ["InlineImage", "attach_inline_images"]
