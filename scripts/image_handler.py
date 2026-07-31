"""Handle images for the newsletter pipeline.

Two image sources:
  1. Embedded in the DOCX (word/media/*) — auto-extracted.
  2. Drop folder /drop-images/ with naming convention
     `s<section#>_<order>_<slug>.<ext>` — placed after the matching section's
     last block.

All images land in /assets/issue-<N>/ and are referenced via GitHub raw URLs.
"""

from __future__ import annotations

import logging
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from scripts.config import RepoConfig

log = logging.getLogger(__name__)


DROP_NAME_RE = re.compile(
    r"^s(?P<section>\d+)_(?P<order>\d+)_(?P<slug>[a-z0-9-]+)\.(?P<ext>jpg|jpeg|png|webp|gif)$",
    re.IGNORECASE,
)


# Magic-byte signatures of supported raster image formats. SVG, HTML, PDF,
# executables and anything else are silently dropped (a malicious DOCX could
# embed an SVG with <script>, which renders in some email clients).
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff",        "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n",   "image/png"),
    (b"GIF87a",              "image/gif"),
    (b"GIF89a",              "image/gif"),
    (b"RIFF",                "image/webp"),  # RIFF...WEBP -- second check below
    (b"BM",                  "image/bmp"),
)


def _is_supported_image(path: Path) -> bool:
    """Return True if `path`'s magic bytes match a supported raster format."""
    try:
        with path.open("rb") as fh:
            head = fh.read(16)
    except OSError:
        return False
    for sig, _mime in _IMAGE_MAGIC:
        if head.startswith(sig):
            if sig == b"RIFF":
                # RIFF must be followed by WEBP at byte 8.
                return head[8:12] == b"WEBP"
            return True
    return False


# Extension -> MIME-type lookup for the formats this module accepts. Used
# by the Outlook backend to write `PR_ATTACH_MIME_TAG` on inline images
# so Gmail web doesn't fall back to "show as attachment". Living here
# (rather than in `outlook.py`) keeps the supported-format knowledge
# single-sourced -- when WebP / AVIF support is toggled in `_IMAGE_MAGIC`,
# this lookup updates in lockstep. Round-12 architect MEDIUM N2.
_EXT_TO_MIME: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".bmp":  "image/bmp",
}


def extension_to_mime(path: str | Path) -> str:
    """Map a file path's extension to its MIME type.

    Returns one of `image/jpeg`, `image/png`, `image/gif`, `image/webp`,
    `image/bmp` for the formats `_IMAGE_MAGIC` accepts; falls back to
    `application/octet-stream` for anything else (the attachment still
    ships, just without inline-disposition nudging).

    Case-insensitive on the extension. Accepts `str` or `Path`.
    """
    if isinstance(path, Path):
        ext = path.suffix.lower()
    else:
        ext = Path(str(path)).suffix.lower()
    return _EXT_TO_MIME.get(ext, "application/octet-stream")


@dataclass(frozen=True)
class DropImage:
    section: int
    order: int
    slug: str
    src_path: Path
    dst_path: Path


def issue_dir(assets_dir: Path, issue: int) -> Path:
    return assets_dir / f"issue-{issue}"


# Per-member ceiling on an extracted image, and the compression ratio
# above which a member is treated as a decompression bomb rather than a
# photograph. Without these, `word/media/x.jpg` holding 400 MB of zeroes
# expands from a 400 KB DOCX -- on the CLI that fills the editor's disk
# and can wedge `publish-images` against GitHub's push limit; in the
# browser it inflates Pyodide's in-memory filesystem until the tab dies.
#
# 25 MB, NOT the 2 MB CID attachment cap. Those are two different limits
# and conflating them was a regression: at 2 MB a photo straight off a
# camera (commonly 3-8 MB) was refused by `extract_embedded` outright,
# so it never reached `url_map`, its `media://` sentinel never resolved,
# and the picture vanished from the newsletter with only a log line.
# The CID cap is about how big an EMAIL should be and correctly leaves
# an oversized photo as a hosted URL; this one is about refusing a
# decompression bomb, and belongs far above any real photograph.
# Compression ratio does the actual bomb detection -- JPEG and PNG are
# already compressed, so legitimate media never approaches 100:1.
_MAX_EMBEDDED_BYTES = 25_000_000
_MAX_COMPRESSION_RATIO = 100
# Ceiling on the total extracted across one DOCX, so a hundred
# individually-legal members cannot add up to the same problem.
_MAX_EMBEDDED_TOTAL_BYTES = 50_000_000

# Photos are resized to fit the email before anything else sees them.
#
# The rendered newsletter displays images at MAX_IMG_PX = 560 px wide.
# A photo straight off a camera or a phone is 1500-6000 px, so every
# recipient's mail client is already downscaling it -- we were shipping
# several times more bytes than anyone could see, and paying for it in
# message size, in mailbox quota, and in load time on a slow connection.
# On the reported production document this turns 1.6 MB of media into
# ~470 KB with no visible difference.
#
# 1200 px is 2x the display width, so the result is still sharp on a
# retina screen. The format is PRESERVED -- a PNG stays a PNG. Resizing
# a diagram is safe (it is displayed at 560 px regardless), but
# re-encoding one as JPEG would introduce ringing around fine text, so
# `quality` applies only to images that were already JPEG.
DEFAULT_MAX_IMAGE_PX = 1200
DEFAULT_IMAGE_QUALITY = 82


def optimize_image(path: Path, *, max_px: int = DEFAULT_MAX_IMAGE_PX,
                   quality: int = DEFAULT_IMAGE_QUALITY) -> tuple[bool, int]:
    """Resize `path` in place to fit `max_px`. Returns (changed, new_size).

    Best-effort by design: if Pillow is missing or the file cannot be
    decoded, the original is left exactly as it was and the caller
    carries on. A newsletter that ships slightly-too-large photos is a
    far better outcome than one that fails to build.

    Two useful side effects of the round-trip, both deliberate:

    * `exif_transpose` bakes in the orientation flag, so a photo taken
      on a phone held sideways is no longer rotated in clients that
      ignore EXIF.
    * EXIF is not carried into the output, which strips GPS coordinates.
      A staff photo taken on a phone routinely carries the exact
      location it was taken; that should not travel to ~50 recipients
      and, in URL mode, onto a public GitHub path.
    """
    before = path.stat().st_size
    try:
        from PIL import Image, ImageOps
    except ImportError:
        log.debug("Pillow not installed; leaving %s at full size.", path.name)
        return False, before

    try:
        with Image.open(path) as im:
            fmt = im.format
            if fmt not in ("JPEG", "PNG"):
                return False, before
            im = ImageOps.exif_transpose(im)
            original_width = im.width
            if original_width <= max_px:
                return False, before

            ratio = max_px / original_width
            resized = im.resize(
                (max_px, max(1, round(im.height * ratio))), Image.LANCZOS)

            if fmt == "JPEG":
                resized.convert("RGB").save(
                    path, "JPEG", quality=quality, optimize=True)
            else:
                resized.save(path, "PNG", optimize=True)
    except Exception as e:  # noqa: BLE001 -- optimisation is best-effort
        log.warning(
            "Could not resize %s (%s); sending it at full size.",
            path.name, e)
        return False, path.stat().st_size if path.exists() else before

    after = path.stat().st_size
    log.info(
        "Resized %s: %d -> %d px wide, %s -> %s bytes.",
        path.name, original_width, max_px, f"{before:,}", f"{after:,}")
    return True, after


def _copy_capped(z: zipfile.ZipFile, name: str, target: Path,
                 limit: int) -> int | None:
    """Stream one member to `target`, aborting past `limit` bytes.

    Returns the byte count, or None if the cap was exceeded.

    The size and ratio gates in `extract_embedded` read `file_size` and
    `compress_size` from the zip's central directory -- i.e. from
    attacker-supplied metadata. CPython does currently cap a member's
    output at the declared `file_size` and then fail the CRC, so an
    understated header truncates rather than expands (verified). But
    that is an implementation detail of `ZipExtFile`, not a guarantee,
    and a security control resting on one is a control that can be
    removed by a patch release nobody reads. This enforces the ceiling
    on bytes we actually wrote, which is true regardless.
    """
    written = 0
    with z.open(name) as src, target.open("wb") as dst:
        while True:
            chunk = src.read(64 * 1024)
            if not chunk:
                return written
            written += len(chunk)
            if written > limit:
                return None
            dst.write(chunk)


def extract_embedded(docx_path: Path, dest_dir: Path, *,
                     max_image_px: int | None = DEFAULT_MAX_IMAGE_PX,
                     image_quality: int = DEFAULT_IMAGE_QUALITY,
                     ) -> dict[str, Path]:
    """Extract images from word/media/ into dest_dir. Return {basename: path}.

    Three independent gates, because each one alone has been shown to be
    insufficient:

    1. **Declared size and compression ratio**, checked BEFORE any bytes
       are written. A zip member is attacker-controlled data and
       `shutil.copyfileobj` will happily stream 400 MB out of a 400 KB
       file.
    2. **Magic bytes**, which reject SVG / HTML / executables whose
       content is not a supported raster format.
    3. **File extension**, which must be one this module recognises as
       an image. Magic bytes alone are NOT enough: the extension is
       preserved verbatim from the DOCX and travels all the way into
       the outgoing email's `Content-Disposition: inline; filename=`.
       A member named `report.hta` whose content begins with the JPEG
       signature passes gate 2, gets attached as
       `application/octet-stream`, and turns the newsletter into a
       delivery vehicle for an executable payload -- sent from the
       editor's own mailbox, to ~50 institutional recipients, carrying
       the newsletter's reputation. Gate 3 closes that.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    total = 0
    with zipfile.ZipFile(docx_path) as z:
        for info in z.infolist():
            name = info.filename
            if not name.startswith("word/media/"):
                continue
            base = Path(name).name

            # Gate 3 first -- it is the cheapest and needs no I/O.
            if Path(base).suffix.lower() not in _EXT_TO_MIME:
                log.warning(
                    "Rejected embedded file %s: %r is not an image "
                    "extension this toolkit accepts. A file with a "
                    "non-image extension must never reach a recipient's "
                    "mailbox as an attachment.",
                    base, Path(base).suffix,
                )
                continue

            # Gate 1 -- refuse before writing anything to disk.
            if info.file_size > _MAX_EMBEDDED_BYTES:
                log.warning(
                    "Rejected embedded file %s: %d bytes exceeds the "
                    "%d-byte cap. Compress the photo in Word "
                    "(right-click -> Compress Pictures) and re-run.",
                    base, info.file_size, _MAX_EMBEDDED_BYTES,
                )
                continue
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > _MAX_COMPRESSION_RATIO:
                log.warning(
                    "Rejected embedded file %s: compression ratio %.0f:1 "
                    "looks like a decompression bomb, not a photograph.",
                    base, ratio,
                )
                continue
            if total + info.file_size > _MAX_EMBEDDED_TOTAL_BYTES:
                log.warning(
                    "Stopped extracting at %s: the DOCX's images exceed "
                    "the %d-byte total cap.",
                    base, _MAX_EMBEDDED_TOTAL_BYTES,
                )
                break

            target = dest_dir / base
            try:
                written = _copy_capped(z, name, target, _MAX_EMBEDDED_BYTES)
            except (zipfile.BadZipFile, OSError, EOFError) as e:
                # A malformed or truncated member must not abort the whole
                # build with a traceback -- in the browser that surfaces
                # to the editor as "a bug in the toolkit". Note a forged
                # size header lands here: CPython truncates the stream at
                # the declared length and then fails the CRC.
                log.warning(
                    "Rejected embedded file %s: could not be read (%s).",
                    base, e)
                target.unlink(missing_ok=True)
                continue
            if written is None:
                log.warning(
                    "Rejected embedded file %s: it kept producing data "
                    "past the %d-byte cap, so its declared size was a "
                    "lie. Treating it as a decompression bomb.",
                    base, _MAX_EMBEDDED_BYTES)
                target.unlink(missing_ok=True)
                continue

            # Gate 2 -- content must actually be a supported raster image.
            if not _is_supported_image(target):
                log.warning(
                    "Rejected embedded file %s (not a supported image format)",
                    base,
                )
                target.unlink(missing_ok=True)
                continue
            # Resize to fit the email before anything downstream sees
            # the file. Doing it HERE means every consumer benefits --
            # the CID attachment, the hosted-URL copy pushed to GitHub,
            # the browser preview's data URI -- without any of them
            # needing to know about it.
            if max_image_px:
                _, new_size = optimize_image(
                    target, max_px=max_image_px, quality=image_quality)
                total += new_size
            else:
                total += target.stat().st_size
            out[base] = target
    return out


def ingest_drop_folder(drop_dir: Path, dest_dir: Path) -> list[DropImage]:
    """Copy validated drop-folder images into dest_dir and return metadata."""
    if not drop_dir.exists():
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[DropImage] = []
    for src in sorted(drop_dir.iterdir()):
        if src.is_dir() or src.name.startswith("."):
            continue
        m = DROP_NAME_RE.match(src.name)
        if not m:
            raise ValueError(
                f"Drop image '{src.name}' does not match expected naming "
                f"convention: s<section#>_<order>_<slug>.<ext> "
                f"(e.g. s2_01_lab.jpg)"
            )
        dst = dest_dir / src.name.lower()
        shutil.copy2(src, dst)
        if not _is_supported_image(dst):
            dst.unlink(missing_ok=True)
            raise ValueError(
                f"Drop image '{src.name}' is not a recognised raster image "
                f"(jpg/png/gif/webp/bmp). Refusing to publish."
            )
        results.append(DropImage(
            section=int(m.group("section")),
            order=int(m.group("order")),
            slug=m.group("slug").lower(),
            src_path=src,
            dst_path=dst,
        ))
    # Stable order: by section then order.
    results.sort(key=lambda d: (d.section, d.order))
    return results


def to_raw_url(asset_path: Path, repo_root: Path, repo: RepoConfig) -> str:
    """Build the GitHub raw URL for a file inside the repo."""
    try:
        rel = asset_path.resolve().relative_to(repo_root.resolve())
    except ValueError as e:
        raise ValueError(
            f"Asset {asset_path} must be inside repo {repo_root}"
        ) from e
    return repo.raw_url(str(rel).replace("\\", "/"))


__all__ = [
    "DROP_NAME_RE", "DropImage",
    "extract_embedded", "ingest_drop_folder", "to_raw_url", "issue_dir",
    "extension_to_mime",
]
