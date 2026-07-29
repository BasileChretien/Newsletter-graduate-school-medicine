"""Guard: the committed web bundle must match the sources it packages.

`web/meridian-bundle.zip` is a *committed binary* holding a copy of
`scripts/`, `templates/`, `locales/` and `images/`. That is what lets
the browser page run the real pipeline from a plain static host with no
build step -- and it is also how the browser build could silently fall
a release behind the CLI: someone fixes a parser bug in `scripts/`,
ships it, and the web page keeps running last month's code.

Running in the normal pytest suite means CI catches the drift on all
three platforms without a bespoke workflow step.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = REPO_ROOT / "web" / "meridian-bundle.zip"
BUILDER = REPO_ROOT / "web" / "build_bundle.py"


def test_the_committed_bundle_is_current():
    """If this fails: `python web/build_bundle.py` and commit the zip."""
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--verify"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_the_bundle_carries_what_the_browser_needs():
    """The four directories `scripts.webapp` reaches for at runtime.

    `images/` is the easy one to forget -- it holds the masthead logo
    and dean photo, which are NOT in the DOCX. Without them the browser
    build still succeeds but quietly emails a logo that recipients
    fetch from GitHub, defeating the point of embedding photos."""
    with zipfile.ZipFile(BUNDLE) as z:
        names = z.namelist()

    assert any(n == "scripts/webapp.py" for n in names)
    assert any(n == "scripts/mail/eml.py" for n in names)
    assert any(n.startswith("templates/") and n.endswith(".j2") for n in names)
    assert any(n.startswith("locales/") for n in names)
    assert any(n.startswith("images/") for n in names)


def test_the_bundle_leaks_no_recipients_or_build_artefacts():
    """`recipients.txt` is gitignored, but a bundle builder that globbed
    too eagerly would publish ~50 real addresses to a static host."""
    with zipfile.ZipFile(BUNDLE) as z:
        names = z.namelist()

    # `scripts/recipients.py` (the loader) belongs in the bundle;
    # `recipients.txt` (the addresses) never does.
    assert not any(Path(n).name == "recipients.txt" for n in names), names
    assert not any(n.endswith(".docx") for n in names), (
        "the bundle ships code and brand assets, not issue content")
    assert not any("__pycache__" in n for n in names)
    assert not any(n.endswith((".pyc", ".pyo")) for n in names)


@pytest.mark.parametrize("asset", ["index.html", "app.js", "style.css"])
def test_the_page_files_exist(asset):
    assert (REPO_ROOT / "web" / asset).is_file()


def test_pyodide_version_is_pinned_to_a_css_inline_capable_line():
    """`css_inline` is the one Rust-backed dependency and the whole
    email layout depends on it. It ships in Pyodide's 0.29.x
    distribution; the 314.x line moved to ABI `2026_0` and has no
    build yet, so an unreviewed version bump breaks the page at
    install time with a message that points at micropip, not at us."""
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/pyodide/v0.29." in html, (
        "Pyodide must stay pinned to the 0.29.x line until css_inline "
        "publishes a build for the newer ABI."
    )
