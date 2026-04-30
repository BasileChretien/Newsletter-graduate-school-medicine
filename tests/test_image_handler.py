"""Tests for image_handler."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.config import RepoConfig
from scripts.image_handler import (
    DROP_NAME_RE, ingest_drop_folder, issue_dir, to_raw_url,
)


def test_drop_name_regex_valid():
    m = DROP_NAME_RE.match("s2_01_lab.jpg")
    assert m
    assert m.group("section") == "2"
    assert m.group("order") == "01"
    assert m.group("slug") == "lab"
    assert m.group("ext").lower() == "jpg"


@pytest.mark.parametrize("name", [
    "lab.jpg", "s2-01-lab.jpg", "s2_01.jpg",
    "s2_01_lab.bmp", "S2_01_lab.JPG",  # last one is allowed (case-insensitive)
])
def test_drop_name_regex_edge_cases(name):
    m = DROP_NAME_RE.match(name)
    if name == "S2_01_lab.JPG":
        assert m is not None
    else:
        assert m is None


def test_ingest_drop_folder_creates_structure(tmp_path: Path):
    drop = tmp_path / "drop-images"
    drop.mkdir()
    (drop / "s1_01_dean.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    (drop / "s4_02_partner.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    dest = tmp_path / "assets" / "issue-1"
    out = ingest_drop_folder(drop, dest)
    assert len(out) == 2
    assert {d.section for d in out} == {1, 4}
    assert all(d.dst_path.exists() for d in out)


def test_ingest_drop_folder_rejects_non_image(tmp_path: Path):
    """A file that matches the naming convention but isn't a real image
    (e.g. an SVG renamed to .png) must be rejected, not published."""
    drop = tmp_path / "drop-images"
    drop.mkdir()
    # SVG content with .png extension -- magic bytes won't match raster.
    (drop / "s1_01_evil.png").write_bytes(b"<svg><script>x</script></svg>")
    with pytest.raises(ValueError, match="not a recognised raster image"):
        ingest_drop_folder(drop, tmp_path / "assets")


def test_ingest_drop_folder_rejects_invalid_name(tmp_path: Path):
    drop = tmp_path / "drop-images"
    drop.mkdir()
    (drop / "junk.jpg").write_bytes(b"x")
    with pytest.raises(ValueError, match="naming convention"):
        ingest_drop_folder(drop, tmp_path / "assets")


def test_ingest_drop_folder_missing_returns_empty(tmp_path: Path):
    assert ingest_drop_folder(tmp_path / "missing", tmp_path / "out") == []


def test_to_raw_url_builds_correct_path(tmp_path: Path):
    repo_root = tmp_path
    asset = repo_root / "assets" / "issue-3" / "s1_01_dean.jpg"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"x")
    cfg = RepoConfig(user="acme", repo="news", branch="main")
    url = to_raw_url(asset, repo_root, cfg)
    assert url == (
        "https://raw.githubusercontent.com/acme/news/main/"
        "assets/issue-3/s1_01_dean.jpg"
    )


def test_to_raw_url_rejects_outside_repo(tmp_path: Path):
    cfg = RepoConfig(user="x", repo="y")
    outside = tmp_path / "elsewhere" / "file.jpg"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"x")
    with pytest.raises(ValueError):
        to_raw_url(outside, tmp_path / "repo", cfg)


def test_issue_dir():
    assert issue_dir(Path("/a/b"), 5) == Path("/a/b/issue-5")


# ---------- extension_to_mime (round-12 N2: lookup moved here from
#            outlook.py to keep the supported-format list single-sourced
#            with `_IMAGE_MAGIC`) -----------------------------------------

def test_extension_to_mime_known_extensions():
    from scripts.image_handler import extension_to_mime
    assert extension_to_mime("photo.jpg") == "image/jpeg"
    assert extension_to_mime("photo.JPG") == "image/jpeg"
    assert extension_to_mime("photo.jpeg") == "image/jpeg"
    assert extension_to_mime("photo.png") == "image/png"
    assert extension_to_mime("photo.gif") == "image/gif"
    assert extension_to_mime("photo.webp") == "image/webp"
    assert extension_to_mime("photo.bmp") == "image/bmp"


def test_extension_to_mime_accepts_path_object():
    """Caller may pass a `Path` (the Outlook backend does)."""
    from scripts.image_handler import extension_to_mime
    assert extension_to_mime(Path("a/b/photo.png")) == "image/png"


def test_extension_to_mime_unknown_extension_returns_octet_stream():
    """Unknown extensions get a generic MIME type so the attachment
    still ships, just without inline-disposition nudging."""
    from scripts.image_handler import extension_to_mime
    assert extension_to_mime("doc.pdf") == "application/octet-stream"
    assert extension_to_mime("noext") == "application/octet-stream"


def test_extension_to_mime_lookup_matches_image_magic_formats():
    """Pin the invariant: every format in `_IMAGE_MAGIC` should have
    a matching extension entry in `_EXT_TO_MIME`. If a future change
    adds AVIF (or anything else) to one but not the other, this
    test fails immediately."""
    from scripts.image_handler import _IMAGE_MAGIC, _EXT_TO_MIME
    magic_mimes = {mime for _sig, mime in _IMAGE_MAGIC}
    ext_mimes = set(_EXT_TO_MIME.values())
    missing_from_ext = magic_mimes - ext_mimes
    assert not missing_from_ext, (
        f"Formats accepted by `_IMAGE_MAGIC` but missing from "
        f"`_EXT_TO_MIME`: {missing_from_ext}. The two lists must "
        "stay in sync -- a format the magic-byte check accepts but "
        "the MIME-tag lookup doesn't will degrade Gmail rendering."
    )
