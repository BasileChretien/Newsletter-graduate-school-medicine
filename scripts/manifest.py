"""Per-issue manifest -- audit trail for what was published when.

Every successful build writes `assets/issue-N/manifest.json` capturing:
  - issue number
  - source DOCX SHA-256 (so re-runs detect content changes)
  - build timestamp (UTC, ISO-8601)
  - file inventory of the issue's assets directory
  - subject line
  - dean info (so a future archive read knows who signed it)

If a previous manifest exists and the new build is for a different DOCX
(different hash), the old manifest is preserved as
`manifest.previous.json`. Editors can see at a glance what was last
published for an issue, and re-publishing now requires intent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts.config import DEAN_NAME, DEAN_TITLE, TITLE

log = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
PREVIOUS_FILENAME = "manifest.previous.json"


@dataclass(frozen=True)
class IssueManifest:
    issue: int
    title: str
    subject: str
    docx_sha256: str
    built_at: str            # ISO-8601 UTC
    dean_name: str
    dean_title: str
    files: tuple[str, ...]
    file_count: int
    image_count: int
    output_html: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n"


def docx_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(*, issue: int, asset_dir: Path, source_docx: Path,
                   subject: str, output_html: Path) -> IssueManifest:
    """Write a manifest.json in `asset_dir`.

    Behaviour:
      - First publish for an issue: stamp current dean info + build time.
      - Re-publish of the SAME content (matching docx_sha256): preserve
        the original `dean_name`, `dean_title`, and `built_at` from the
        existing manifest -- audit trail integrity. Subject and file
        inventory are refreshed.
      - Re-publish of DIFFERENT content (hash mismatch): archive the
        previous manifest as `manifest.previous.json` and stamp fresh.
    """
    asset_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        f.name for f in asset_dir.iterdir() if f.is_file()
        and f.name not in (MANIFEST_FILENAME, PREVIOUS_FILENAME)
    )
    image_count = sum(1 for f in files if f.lower().endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
    ))
    new_hash = docx_hash(source_docx)

    # Default values (used when there's no prior manifest).
    dean_name = DEAN_NAME
    dean_title = DEAN_TITLE
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_path = asset_dir / MANIFEST_FILENAME
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old.get("docx_sha256") == new_hash:
                # Same content as before -- preserve original audit data.
                dean_name = old.get("dean_name") or dean_name
                dean_title = old.get("dean_title") or dean_title
                built_at = old.get("built_at") or built_at
                log.debug("Re-publishing same content for issue %d -- "
                          "preserving original dean + built_at fields.",
                          issue)
            else:
                # Different content -- archive the old manifest.
                (asset_dir / PREVIOUS_FILENAME).write_text(
                    json.dumps(old, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                log.warning(
                    "Issue %d already had a manifest with a different DOCX "
                    "hash. Old manifest archived as %s.",
                    issue, PREVIOUS_FILENAME,
                )
        except Exception as e:
            log.debug("Could not read previous manifest: %s", e)

    new = IssueManifest(
        issue=issue,
        title=TITLE,
        subject=subject,
        docx_sha256=new_hash,
        built_at=built_at,
        dean_name=dean_name,
        dean_title=dean_title,
        files=tuple(files),
        file_count=len(files),
        image_count=image_count,
        output_html=output_html.name,
    )
    manifest_path.write_text(new.to_json(), encoding="utf-8")
    return new


def load_manifest(asset_dir: Path) -> IssueManifest | None:
    """Return the manifest for an issue's asset dir, or None if missing
    or unreadable. Robust against corrupted / null fields."""
    p = asset_dir / MANIFEST_FILENAME
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return IssueManifest(
            issue=int(data.get("issue") or 0),
            title=data.get("title") or "",
            subject=data.get("subject") or "",
            docx_sha256=data.get("docx_sha256") or "",
            built_at=data.get("built_at") or "",
            dean_name=data.get("dean_name") or "",
            dean_title=data.get("dean_title") or "",
            files=tuple(data.get("files") or ()),
            file_count=int(data.get("file_count") or 0),
            image_count=int(data.get("image_count") or 0),
            output_html=data.get("output_html") or "",
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        log.debug("Could not parse manifest at %s: %s", p, e)
        return None


__all__ = [
    "IssueManifest", "MANIFEST_FILENAME", "PREVIOUS_FILENAME",
    "docx_hash", "write_manifest", "load_manifest",
]
