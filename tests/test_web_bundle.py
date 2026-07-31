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

import re
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


def test_zip_metadata_is_platform_independent():
    """`ZipInfo.create_system` defaults to 0 (MS-DOS) on Windows and 3
    (Unix) elsewhere, and it is written into the header -- so identical
    content produced two different files depending on who ran the
    builder. That is what first broke this suite on the Linux and macOS
    CI runners."""
    with zipfile.ZipFile(BUNDLE) as z:
        infos = z.infolist()

    assert {i.create_system for i in infos} == {3}
    assert {i.date_time for i in infos} == {(1980, 1, 1, 0, 0, 0)}
    # Archive names must be POSIX-separated whoever packed them.
    assert not any("\\" in i.filename for i in infos)


def test_entries_are_sorted_by_posix_name():
    """`Path` ordering is case-folded and backslash-separated on
    Windows, case-sensitive and slash-separated elsewhere, so sorting
    by `Path` could pack the same tree in two different orders."""
    with zipfile.ZipFile(BUNDLE) as z:
        names = z.namelist()

    assert names == sorted(names)


def test_bundled_text_is_lf_normalised():
    """Determinism across checkouts. With `core.autocrlf=true` a Windows
    working tree holds CRLF and a Linux one holds LF, so a bundle that
    packed raw bytes could never match a rebuild on the other platform
    -- and CI runs `--verify` on all three."""
    with zipfile.ZipFile(BUNDLE) as z:
        offenders = [
            n for n in z.namelist()
            if Path(n).suffix.lower() in {".py", ".j2", ".css", ".toml"}
            and b"\r\n" in z.read(n)
        ]
    assert offenders == [], offenders


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
    # The version pin and the integrity hash must travel together. A
    # bump that KEEPS a stale hash fails safe -- the page simply will not
    # boot -- but a bump that DROPS the attribute silently removes the
    # only check on the code that reads the editor's document.
    tag = re.search(
        r"<script[^>]*pyodide/v0\.29\.\d+/full/pyodide\.js[^>]*>", html, re.S)
    assert tag, "Pyodide <script> tag not found"
    assert re.search(r'integrity="sha384-[A-Za-z0-9+/=]{60,}"', tag.group(0)), (
        "the Pyodide <script> tag must carry a sha384 integrity hash"
    )
    assert 'crossorigin="anonymous"' in tag.group(0), (
        "SRI is silently inert without crossorigin=anonymous"
    )


def test_the_page_declares_a_content_security_policy():
    """The page's headline promise is that the editor's document is never
    uploaded. Without a CSP that is enforced only by intent; with one,
    `connect-src` is an allowlist and a backdoored dependency has
    nowhere to send a DOCX or a recipient list."""
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "Content-Security-Policy" in html
    assert "form-action 'none'" in html
    csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', html)
    assert csp, "CSP must be a single quoted content attribute"
    connect = re.search(r"connect-src ([^;]+);", csp.group(1))
    assert connect, "CSP must constrain connect-src"
    # Whatever hosts are allowed, a wildcard would defeat the point.
    assert "*" not in connect.group(1)


def test_python_dependencies_fetched_from_pypi_are_version_pinned():
    """Packages absent from Pyodide's own lockfile resolve against PyPI
    at every cold load. Unpinned, that executes whatever was released
    this morning inside the tab holding an unpublished newsletter and
    the recipient list."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    assert packages, "PY_PACKAGES list not found"

    assert re.search(r'"python-docx==\d+\.\d+', packages.group(1)), (
        "python-docx is not in Pyodide's distribution, so it comes from "
        "PyPI and must carry an exact version pin."
    )


def test_hidden_elements_are_not_defeated_by_a_display_rule():
    """The `hidden` attribute is implemented by the browser as
    `[hidden] { display: none }` in its own stylesheet, and ANY author
    rule beats a UA rule. `.boot { display: flex }` therefore silently
    defeated `<div id="boot" hidden>`: the live page told the editor it
    was still "Loading the MERIDIAN toolkit…" long after boot finished,
    with a "Building…" spinner stuck beside a button they had not
    pressed. The app worked; it just described itself incorrectly.

    This checks the actual interaction rather than merely asserting the
    override exists: for every element in index.html that carries
    `hidden`, if any CSS rule sets `display` for one of its classes,
    then a global `[hidden]` override with `!important` must be present
    to win against it.
    """
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (REPO_ROOT / "web" / "style.css").read_text(encoding="utf-8")

    # Classes on elements that are toggled via the `hidden` attribute.
    # Scanned one tag at a time: a pattern that walks past `>` merges a
    # tag with the one after it and collects the neighbour's classes.
    # Within a tag, `hidden` must be a standalone attribute -- a bare
    # `\bhidden\b` also matches `aria-hidden="true"`, because `-` counts
    # as a word boundary, which pulled in `.spinner`.
    hidden_classes: set[str] = set()
    for tag in re.findall(r"<[^>]+>", html):
        if not re.search(r"(?<![\w-])hidden(?=[\s=>/])", tag):
            continue
        m = re.search(r'class="([^"]+)"', tag)
        if m:
            hidden_classes.update(m.group(1).split())

    # Classes that some rule gives an explicit `display`.
    display_classes = {
        cls for cls in hidden_classes
        if re.search(rf"\.{re.escape(cls)}\b[^{{]*{{[^}}]*\bdisplay\s*:", css)
    }

    if display_classes:
        assert re.search(r"\[hidden\][^{]*{[^}]*display\s*:\s*none\s*!important",
                         css), (
            "these classes set `display` and are used on elements toggled by "
            f"the `hidden` attribute: {sorted(display_classes)}. Without a "
            "global `[hidden] { display: none !important }` they stay "
            "visible even when hidden is set."
        )


def test_desktop_and_browser_parse_with_the_same_python_docx():
    """The two builds must parse the editor's document with the same
    library version. They had silently diverged (desktop 1.1.2, browser
    1.2.0), which undercuts the "no parallel implementation to drift"
    guarantee the bundle exists to provide -- the .eml a browser editor
    sends would not have come from the same stack as a desktop one."""
    reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    desktop = re.search(r"^python-docx==([\d.]+)", reqs, re.M)
    browser = re.search(r'"python-docx==([\d.]+)"', app_js)
    assert desktop and browser, "could not find both pins"
    assert desktop.group(1) == browser.group(1), (
        f"requirements.txt pins {desktop.group(1)} but web/app.js pins "
        f"{browser.group(1)}")
