"""Tests for the per-issue manifest writer."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.manifest import (
    MANIFEST_FILENAME, PREVIOUS_FILENAME, docx_hash,
    load_manifest, write_manifest,
)


def _seed_assets(asset_dir: Path) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "image1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    (asset_dir / "image2.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")


def test_write_manifest_creates_file(tmp_path: Path):
    asset_dir = tmp_path / "assets" / "issue-1"
    _seed_assets(asset_dir)
    docx = tmp_path / "issue-1.docx"
    docx.write_bytes(b"PK\x03\x04 fake docx")
    output = tmp_path / "dist" / "issue-1.html"
    output.parent.mkdir(parents=True)
    output.write_text("<html></html>", encoding="utf-8")

    m = write_manifest(
        issue=1, asset_dir=asset_dir, source_docx=docx,
        subject="MERIDIAN -- Test", output_html=output,
    )
    assert m.issue == 1
    assert m.subject == "MERIDIAN -- Test"
    assert len(m.docx_sha256) == 64
    assert m.image_count == 2
    assert (asset_dir / MANIFEST_FILENAME).exists()


def test_write_manifest_archives_previous_on_content_change(tmp_path: Path):
    asset_dir = tmp_path / "assets" / "issue-2"
    _seed_assets(asset_dir)
    docx = tmp_path / "issue-2.docx"
    docx.write_bytes(b"first")
    output = tmp_path / "dist" / "issue-2.html"
    output.parent.mkdir(parents=True)
    output.write_text("<x/>", encoding="utf-8")

    write_manifest(issue=2, asset_dir=asset_dir, source_docx=docx,
                   subject="A", output_html=output)
    docx.write_bytes(b"second -- different content")
    write_manifest(issue=2, asset_dir=asset_dir, source_docx=docx,
                   subject="B", output_html=output)

    assert (asset_dir / PREVIOUS_FILENAME).exists()
    archived = json.loads(
        (asset_dir / PREVIOUS_FILENAME).read_text(encoding="utf-8"))
    assert archived["subject"] == "A"


def test_load_manifest_round_trip(tmp_path: Path):
    asset_dir = tmp_path / "assets" / "issue-3"
    _seed_assets(asset_dir)
    docx = tmp_path / "issue-3.docx"
    docx.write_bytes(b"hello")
    output = tmp_path / "dist" / "issue-3.html"
    output.parent.mkdir(parents=True)
    output.write_text("<x/>", encoding="utf-8")

    written = write_manifest(
        issue=3, asset_dir=asset_dir, source_docx=docx,
        subject="Round-trip", output_html=output,
    )
    loaded = load_manifest(asset_dir)
    assert loaded is not None
    assert loaded.issue == 3
    assert loaded.subject == "Round-trip"
    assert loaded.docx_sha256 == written.docx_sha256


def test_docx_hash_stable(tmp_path: Path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert docx_hash(p) == docx_hash(p)


def test_write_manifest_preserves_audit_data_on_same_hash(tmp_path: Path):
    """Re-running the build for the same DOCX must NOT re-stamp dean_name
    or built_at -- audit-trail integrity if the dean changes mid-issue."""
    asset_dir = tmp_path / "assets" / "issue-7"
    _seed_assets(asset_dir)
    docx = tmp_path / "issue-7.docx"
    docx.write_bytes(b"unchanged content")
    output = tmp_path / "dist" / "issue-7.html"
    output.parent.mkdir(parents=True)
    output.write_text("<x/>", encoding="utf-8")

    first = write_manifest(
        issue=7, asset_dir=asset_dir, source_docx=docx,
        subject="First", output_html=output,
    )
    # Simulate a global config change between runs.
    import scripts.manifest as mod
    original_dean = mod.DEAN_NAME
    try:
        mod.DEAN_NAME = "Prof. Different Dean"
        mod.DEAN_TITLE = "New Title"
        second = write_manifest(
            issue=7, asset_dir=asset_dir, source_docx=docx,
            subject="Second build, same content", output_html=output,
        )
    finally:
        mod.DEAN_NAME = original_dean

    # Subject DID get refreshed; dean info DID NOT.
    assert second.subject == "Second build, same content"
    assert second.dean_name == first.dean_name == "Prof. Masahisa Katsuno"
    assert second.built_at == first.built_at
