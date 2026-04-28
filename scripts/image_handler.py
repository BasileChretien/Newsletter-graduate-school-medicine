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


@dataclass(frozen=True)
class DropImage:
    section: int
    order: int
    slug: str
    src_path: Path
    dst_path: Path


def issue_dir(assets_dir: Path, issue: int) -> Path:
    return assets_dir / f"issue-{issue}"


def extract_embedded(docx_path: Path, dest_dir: Path) -> dict[str, Path]:
    """Extract images from word/media/ into dest_dir. Return {basename: path}.

    Files whose magic bytes don't match a supported raster format are
    rejected -- this prevents a crafted DOCX from smuggling SVG, HTML,
    or executables into the public assets/issue-N/ directory.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if not name.startswith("word/media/"):
                continue
            base = Path(name).name
            target = dest_dir / base
            with z.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if not _is_supported_image(target):
                log.warning(
                    "Rejected embedded file %s (not a supported image format)",
                    base,
                )
                target.unlink(missing_ok=True)
                continue
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
]
