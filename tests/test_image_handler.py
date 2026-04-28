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
    (drop / "s4_02_partner.png").write_bytes(b"\x89PNGfake")
    dest = tmp_path / "assets" / "issue-1"
    out = ingest_drop_folder(drop, dest)
    assert len(out) == 2
    assert {d.section for d in out} == {1, 4}
    assert all(d.dst_path.exists() for d in out)


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
