"""The browser runtime can still be fetched after its upstream copy is gone.

`web/vendor_pyodide.py` downloads the Pyodide runtime and the wheels the
page loads at every deploy, and checks each file against the committed
SHA-256 hashes in `web/pyodide-assets.json`. Those files came only from
jsDelivr (whose `/pyodide/` path carries no retention promise) and PyPI.
If either dropped them, every later deploy would fail and the live site
would be frozen on its last good version.

So every file now has a second source: a permanent copy published as the
assets of one GitHub Release in this repository per runtime version
(`.github/workflows/mirror-runtime.yml`). The hash file stays the single
authority -- neither source is trusted for bytes that do not match it.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def vendor():
    sys.path.insert(0, str(REPO_ROOT / "web"))
    try:
        import vendor_pyodide
    finally:
        sys.path.pop(0)
    return vendor_pyodide


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------- where the mirror is ----------
def test_the_mirror_is_this_repository_s_release_for_the_pinned_runtime(
    vendor, monkeypatch,
):
    monkeypatch.delenv("MERIDIAN_RUNTIME_MIRROR", raising=False)
    assert vendor.mirror_base() == (
        "https://github.com/BasileChretien/Newsletter-graduate-school-medicine"
        f"/releases/download/pyodide-runtime-{vendor.PYODIDE_VERSION}/")


def test_a_fork_can_point_at_its_own_mirror(vendor, monkeypatch):
    monkeypatch.setenv("MERIDIAN_RUNTIME_MIRROR", "https://example.org/runtime")
    assert vendor.mirror_base() == "https://example.org/runtime/"


# ---------- fetching with a fallback ----------
def test_a_file_the_cdn_no_longer_serves_comes_from_the_mirror(vendor, monkeypatch):
    real = b"runtime bytes"
    asked = []

    def fetch(url):
        asked.append(url)
        if url.startswith("https://cdn.example/"):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return real

    monkeypatch.setattr(vendor, "_fetch", fetch)
    data = vendor.fetch_verified(
        "pyodide.asm.wasm",
        ["https://cdn.example/pyodide.asm.wasm", "https://mirror.example/pyodide.asm.wasm"],
        expected=_digest(real))
    assert data == real
    assert asked == ["https://cdn.example/pyodide.asm.wasm",
                     "https://mirror.example/pyodide.asm.wasm"]


def test_a_cdn_serving_changed_bytes_falls_back_to_the_mirror(vendor, monkeypatch):
    real = b"real"
    monkeypatch.setattr(
        vendor, "_fetch",
        lambda url: b"changed" if url.startswith("https://cdn.example/") else real)
    assert vendor.fetch_verified(
        "pyodide.js", ["https://cdn.example/pyodide.js", "https://mirror.example/pyodide.js"],
        expected=_digest(real)) == real


def test_bytes_that_match_no_hash_are_accepted_from_neither_source(vendor, monkeypatch):
    monkeypatch.setattr(vendor, "_fetch", lambda url: b"tampered")
    with pytest.raises(RuntimeError, match="pyodide.js"):
        vendor.fetch_verified(
            "pyodide.js", ["https://cdn.example/x", "https://mirror.example/x"],
            expected=_digest(b"real"))


def test_without_a_recorded_hash_the_first_source_that_answers_wins(vendor, monkeypatch):
    """`--write-hashes` after a version bump has nothing to compare with yet."""
    def fetch(url):
        if url.startswith("https://cdn.example/"):
            raise OSError("down")
        return b"from the mirror"
    monkeypatch.setattr(vendor, "_fetch", fetch)
    assert vendor.fetch_verified(
        "a-1.0-py3-none-any.whl", ["https://cdn.example/a", "https://mirror.example/a"],
        expected=None) == b"from the mirror"


def test_when_every_source_fails_the_error_names_each_one(vendor, monkeypatch):
    def down(url):
        raise OSError(f"unreachable: {url}")
    monkeypatch.setattr(vendor, "_fetch", down)
    with pytest.raises(RuntimeError) as error:
        vendor.fetch_verified(
            "pyodide.js", ["https://cdn.example/x", "https://mirror.example/x"],
            expected=None)
    message = str(error.value)
    assert "pyodide.js" in message
    assert "https://cdn.example/x" in message and "https://mirror.example/x" in message


def test_every_file_has_the_mirror_as_its_second_source(vendor, monkeypatch):
    """Core files, wheels resolved from the lockfile and wheels from PyPI."""
    monkeypatch.delenv("MERIDIAN_RUNTIME_MIRROR", raising=False)
    sources = {}
    lock = {"packages": {
        name: {"file_name": f"{name.replace('-', '_')}-1.0-py3-none-any.whl",
               "depends": []}
        for name in vendor.PACKAGES}}

    def fetch_verified(name, urls, expected):
        sources[name] = list(urls)
        return json.dumps(lock).encode() if name == "pyodide-lock.json" else b"x"

    monkeypatch.setattr(vendor, "fetch_verified", fetch_verified)
    vendor.collect(expected={})

    assert set(vendor.CORE_FILES) <= set(sources)
    assert set(vendor.PYPI_WHEELS) <= set(sources)
    assert len(sources) == len(vendor.CORE_FILES) + len(vendor.PACKAGES) + len(vendor.PYPI_WHEELS)
    for name, urls in sources.items():
        assert len(urls) == 2, name
        assert urls[-1] == vendor.mirror_base() + name, name


# ---------- the workflow that fills the mirror ----------
def test_the_mirror_workflow_publishes_verified_files_as_a_prerelease():
    workflow = (REPO_ROOT / ".github" / "workflows" / "mirror-runtime.yml").read_text(
        encoding="utf-8")
    # It creates the release and uploads assets, and needs nothing more.
    assert "permissions:\n  contents: write\n" in workflow
    # The files are fetched AND checked against the committed hashes first.
    assert "python web/vendor_pyodide.py" in workflow
    assert "web/pyodide/*" in workflow
    # A pre-release is never shown as MERIDIAN's "Latest" release, so the
    # README's release badge and link keep pointing at real releases.
    assert "--prerelease" in workflow
    assert "pyodide-runtime-" in workflow


def test_the_deploy_job_does_not_gain_write_access():
    """Uploading the mirror lives in its own workflow so that the deploy,
    which publishes the page, keeps its narrow permissions."""
    deploy = (REPO_ROOT / ".github" / "workflows" / "deploy-web.yml").read_text(
        encoding="utf-8")
    assert "contents: write" not in deploy
