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

import json
import re
import shutil
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


# The Pyodide ABI in a compiled wheel's filename: `2026_0` in
# `lxml-6.1.3-cp314-cp314-pyemscripten_2026_0_wasm32.whl`. Older
# lockfiles spelled the platform `pyodide_<abi>`.
_WHEEL_ABI = re.compile(r"-(?:pyemscripten|pyodide)_(\d{4}_\d+)_wasm32\.whl$")


def test_pyodide_version_is_pinned_to_a_css_inline_capable_line():
    """`css_inline` is the one Rust-backed dependency the page vendors,
    and the whole email layout depends on it. A compiled wheel loads only
    into the Pyodide ABI it was built for, and Pyodide changes ABI about
    once a year (0.29.x is `2025_0`, 314.x is `2026_0`). A version bump
    that leaves css-inline on the previous line's build breaks the page
    at install time, with a message that points at the loader, not at us.

    The runtime's own ABI shows in the wheels its lockfile supplies (lxml,
    markupsafe, pillow). So every compiled wheel in the hash file has to
    carry one and the same ABI; `--write-hashes` after a bump that forgot
    css-inline records two."""
    src = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(encoding="utf-8")
    pinned = re.search(r'^PYODIDE_VERSION = "([^"]+)"', src, re.M).group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned), (
        f"PYODIDE_VERSION {pinned!r} is not a final release")
    # The script and the hash file must agree, or the deploy fetches one
    # version and checks it against another. That fails closed, but only
    # after someone has already pushed to main.
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    assert assets["pyodide_version"] == pinned

    abis = {name: m.group(1) for name in assets["files"]
            if (m := _WHEEL_ABI.search(name))}
    assert any(name.startswith("css_inline-") for name in abis), (
        "no compiled css_inline wheel is vendored")
    assert any(not name.startswith("css_inline-") for name in abis), (
        "no lockfile wheel shows the runtime's own ABI")
    assert len(set(abis.values())) == 1, (
        f"the vendored wheels are built for different Pyodide ABIs: {abis}. "
        f"Switch css-inline in PYPI_WHEELS and PY_PACKAGES to its build for "
        f"Pyodide {pinned}'s ABI.")


def test_the_page_loads_only_wheels_the_deploy_vendors():
    """A wheel loaded by path that the deploy does not vendor is a 404 at
    boot -- and Pyodide logs a failed package and carries on, so the page
    can still report ready. Each path in `PY_PACKAGES` has to be a file
    the hash file pins; that also carries the ABI check above over to
    what the page actually loads."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    loaded = [path.rsplit("/", 1)[-1] for path in
              re.findall(r'"\./pyodide/([^"]+\.whl)"', packages.group(1))]
    assert loaded, "PY_PACKAGES loads no wheel by path"
    missing = [wheel for wheel in loaded if wheel not in assets["files"]]
    assert not missing, (
        f"web/app.js loads wheels the deploy does not vendor: {missing}")


def test_a_package_that_fails_to_load_stops_the_boot():
    """`pyodide.loadPackage` does not reject when a wheel fails: it
    reports the failure through `errorCallback` and resolves. Most losses
    still kill the boot at `from scripts.webapp import ...`, but Pillow is
    optional in the toolkit -- without it photos go out at full size. With
    the pillow wheel deleted, the page said "Ready to send" and a real
    issue's .eml grew from 2.53 MB to 3.23 MB, with no warning anywhere.

    So the boot has to collect those errors and throw before the page
    reports ready, which lands in the catch that shows `bootFailed`."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    boot = re.search(r"async function boot\(\) \{.*?\n\}", app_js, re.S)
    assert boot, "boot() not found in web/app.js"
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", boot.group(0), flags=re.S)

    call = re.search(r"await pyodide\.loadPackage\(PY_PACKAGES,\s*\{(.*?)\}\);",
                     body, re.S)
    assert call, "loadPackage must be given an options object"
    collector = re.search(r"errorCallback:\s*\(?(\w+)\)?\s*=>\s*(\w+)\.push\(\1\)",
                          call.group(1))
    assert collector, "load errors are not collected through errorCallback"
    # An options object replaces the default `{ checkIntegrity: true }`.
    assert re.search(r"checkIntegrity:\s*true", call.group(1)), (
        "passing options must not switch off the lockfile hash check")

    errors = re.escape(collector.group(2))
    stop = re.search(rf"if \({errors}\.length\) \{{\s*throw new Error\(", body)
    assert stop, "collected load errors never stop the boot"
    assert call.end() < stop.start() < body.index("buildFn = pyodide.runPython"), (
        "load errors must be checked after loadPackage and before the page "
        "reports ready")
    catch = re.search(r"\} catch \(err\) \{.*", body, re.S).group(0)
    assert re.search(r'"bootFailed",\s*String\(err\)\)', catch), (
        "a boot failure must show bootFailed with the error as its detail")


def test_the_runtime_is_served_from_this_origin():
    """Every executed byte comes from our own host. The previous
    arrangement loaded ~10 MB from `cdn.jsdelivr.net`, which also serves
    `/npm/<any-package>` and `/gh/<any-user>/<any-repo>` -- verified
    live, an arbitrary npm package executed on this page. And SRI covered
    only the 18.5 KB loader: the wasm, the stdlib and every wheel it then
    fetched were unchecked, about 99.8% of the executed bytes.

    This asserts the CDN's *absence* as well as the local path's
    presence. Adding `./pyodide/` while leaving a CDN <script> in place
    would satisfy a presence-only check and change nothing.
    """
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    tags = re.findall(r'<script[^>]*\ssrc="([^"]+)"', html)
    assert tags, "no <script src> found"
    for src in tags:
        assert not re.match(r"(https?:)?//", src), (
            f"{src} is loaded from a third-party host; `script-src "
            f"'self'` exists precisely to forbid that"
        )
    assert any(re.fullmatch(r"\./pyodide/[^/]+/pyodide\.js", src) for src in tags)

    # Without an explicit indexURL the loader falls back to the CDN for
    # the wasm, the stdlib and every wheel -- the <script> tag alone
    # moves only 18.5 KB of the 16 MB.
    assert "loadPyodide({ indexURL: PYODIDE_INDEX_URL })" in app_js
    assert re.search(r'PYODIDE_INDEX_URL = "\./pyodide/[^"/]+/"', app_js)


def _pinned_pyodide_version() -> str:
    src = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(encoding="utf-8")
    return re.search(r'^PYODIDE_VERSION = "([^"]+)"', src, re.M).group(1)


# A string literal (kept) or an HTML / JavaScript comment (dropped). Strings
# are tried first at each position, so a `//` inside one -- a URL, a path --
# is never taken for the start of a comment and the rest of its line lost.
_STRING_OR_COMMENT = re.compile(
    r"""("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)"""
    r"|<!--.*?-->|/\*.*?\*/|//[^\n]*", re.S)


def _code(path: str) -> str:
    """A file with its HTML and JavaScript comments removed: those may
    mention `./pyodide/` in prose, and only code decides what the page
    fetches."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    return _STRING_OR_COMMENT.sub(lambda m: m.group(1) or "", text)


def test_every_runtime_url_carries_the_pinned_pyodide_version():
    """The service worker answers runtime URLs from its cache first, and
    the runtime's own filenames (`pyodide.js`, `pyodide.asm.wasm`, ...)
    are the same in every Pyodide version. While all versions shared
    `./pyodide/`, the first visit after an upgrade -- still controlled by
    the previous worker, with the previous runtime in its cache -- booted
    that runtime: a test of the 0.29.4 -> 314 move ran 0.29.4 with 314's
    css-inline wheel. Each version is now served from
    `./pyodide/<version>/`, URLs that no cache has seen.

    That holds only while every URL the page loads the runtime by moves
    with the pin: the loader in index.html, PYODIDE_INDEX_URL and each
    wheel loaded by path. One left behind is a 404 on the new deploy or,
    for the loader, one version's runtime reading another's files. The
    worker names no version at all; the page tells it which to warm."""
    pinned = _pinned_pyodide_version()
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    assert assets["pyodide_version"] == pinned, (
        "web/pyodide-assets.json and PYODIDE_VERSION name different versions")
    directory = f"./pyodide/{pinned}/"
    html, app_js, sw = (_code(f"web/{name}")
                        for name in ("index.html", "app.js", "sw.js"))
    fix = (f"Move every `./pyodide/<version>/` in web/index.html and "
           f"web/app.js to {directory} (PYODIDE_VERSION in "
           f"web/vendor_pyodide.py).")

    # Where it has to be...
    assert f"{directory}pyodide.js" in re.findall(
        r'<script[^>]*\ssrc="([^"]+)"', html), f"index.html's loader. {fix}"
    assert f'const PYODIDE_INDEX_URL = "{directory}";' in app_js, (
        f"PYODIDE_INDEX_URL in app.js. {fix}")
    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    by_path = [e for e in re.findall(r'"([^"]+)"', packages.group(1)) if "/" in e]
    assert by_path, "PY_PACKAGES loads no wheel by path"
    assert all(e.startswith(directory) for e in by_path), (
        f"wheels in PY_PACKAGES outside {directory}: {by_path}. {fix}")

    # ...and nothing names another: a version left behind, or the flat
    # `./pyodide/` of before.
    runtime_url = re.compile(r"""["'`](\./pyodide/[^"'`]*)["'`]""")
    elsewhere = [
        f"web/{name}: {url}"
        for name, text in (("index.html", html), ("app.js", app_js))
        for url in runtime_url.findall(text)
        if not url.startswith(directory) or "/" in url[len(directory):]]
    assert not elsewhere, f"runtime URLs outside {directory}: {elsewhere}. {fix}"
    assert runtime_url.findall(sw) == ["./pyodide/"], (
        "web/sw.js names a runtime directory; it must take the version from "
        "the page's warm message, or one release's worker warms another's "
        "runtime")

    # The engine test loads what the page names, not a path of its own.
    runner = _code("tests/web_engine/run.cjs")
    assert "PYODIDE_INDEX_URL" in runner
    assert not re.search(r'"pyodide"|\./pyodide/', runner), (
        "tests/web_engine/run.cjs builds its own runtime path")


def test_no_package_is_resolved_over_the_network_at_runtime():
    """micropip reaches PyPI on every cold load. Vendoring removes the
    need for it, and `connect-src 'self'` would block it anyway -- so a
    re-introduced micropip call is a page that boots on a developer's
    machine and hangs on the live one."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", app_js, flags=re.S)
    assert "micropip" not in code, "micropip needs network access"

    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    assert packages, "PY_PACKAGES list not found"
    entries = re.findall(r'"([^"]+)"', packages.group(1))

    # `lxml` has to be named explicitly: python-docx is loaded by PATH,
    # so the lockfile resolver never sees its requirements and pulls
    # nothing in for it. Omitting it produced a page that reported every
    # package loaded and then died on `from lxml import etree` -- caught
    # in the browser, not by the suite, which is why it is pinned here.
    assert "lxml" in entries, (
        "python-docx is loaded by path, so its dependencies are not "
        "resolved for it -- lxml must be requested by name"
    )

    for entry in entries:
        assert not re.match(r"(https?:)?//", entry), entry
        # A bare name resolves out of the vendored lockfile; a wheel must
        # be a local path. Neither may carry a `==` requirement spec,
        # which only micropip understands.
        assert "==" not in entry, (
            f"{entry} is a PyPI requirement spec -- loadPackage takes a "
            f"lockfile name or a path to a vendored wheel"
        )
        if entry.endswith(".whl"):
            assert entry.startswith("./pyodide/"), entry


def test_every_vendored_file_has_a_committed_hash():
    """`pyodide-assets.json` is the only thing standing between the
    deploy and whatever the CDN happens to serve that morning, because
    the bytes themselves are deliberately not in git history."""
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    files = assets["files"]

    for required in ("pyodide.js", "pyodide.asm.wasm", "python_stdlib.zip",
                     "pyodide-lock.json"):
        assert required in files, f"{required} is unverified"
    for name, digest in files.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{name}: {digest!r}"

    # `lxml` is the one that is easy to lose: it is a dependency of
    # python-docx, which is absent from the lockfile, so resolution never
    # reaches it. Omitting it produced a vendor directory that looked
    # complete and then failed at `import docx` in the browser.
    joined = " ".join(files)
    for wheel in ("css_inline", "python_docx", "lxml"):
        assert wheel in joined, f"no {wheel} wheel is vendored"


def test_the_vendored_runtime_is_not_committed():
    """~16 MB against a 5.5 MB repo -- and the README tells editors to
    download that repo as a ZIP, so committing it would nearly triple the
    download for the desktop workflow to benefit the browser one."""
    tracked = subprocess.run(
        ["git", "ls-files", "web/pyodide"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert tracked.stdout.strip() == "", (
        "web/pyodide/ is fetched at deploy time and must stay untracked:\n"
        + tracked.stdout
    )


def test_the_deploy_workflow_vendors_before_it_publishes():
    """Without this step the published site has no `./pyodide/` at all
    and the page 404s on its own loader."""
    wf = (REPO_ROOT / ".github" / "workflows" / "deploy-web.yml").read_text(
        encoding="utf-8")
    assert "web/vendor_pyodide.py" in wf
    assert wf.index("web/vendor_pyodide.py") < wf.index("upload-pages-artifact")
    # Verify mode, not `--write-hashes`: a deploy that rewrote the hashes
    # would rubber-stamp whatever it had just downloaded.
    assert "--write-hashes" not in wf


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
    policy = csp.group(1)
    for directive in ("script-src", "connect-src"):
        found = re.search(rf"{directive} ([^;]+)", policy)
        assert found, f"CSP must constrain {directive}"
        sources = found.group(1).split()
        # Now that the runtime is vendored, neither needs a host at all.
        # `'wasm-unsafe-eval'` is unavoidable -- Pyodide IS a wasm
        # runtime -- but it grants no network reach.
        assert set(sources) <= {"'self'", "'wasm-unsafe-eval'"}, (
            f"{directive} allows {sources}; everything is served from "
            f"this origin, so nothing external needs permitting"
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
    vendor = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(
        encoding="utf-8")

    desktop = re.search(r"^python-docx==([\d.]+)", reqs, re.M)
    # The browser version now lives in a vendored wheel filename rather
    # than a micropip requirement spec. Three places have to agree: the
    # wheel the deploy fetches, the path the page loads, and the desktop
    # pin. A mismatch between the first two is a 404 at boot; a mismatch
    # with the third is the silent divergence this test exists for.
    fetched = re.search(r'"python_docx-([\d.]+)-py3-none-any\.whl"', vendor)
    browser = re.search(
        r'"\./pyodide/(?:[^"/]+/)*python_docx-([\d.]+)-py3-none-any\.whl"', app_js)
    assert desktop and browser and fetched, "could not find all three pins"
    assert desktop.group(1) == browser.group(1) == fetched.group(1), (
        f"requirements.txt pins {desktop.group(1)}, web/app.js loads "
        f"{browser.group(1)}, vendor_pyodide.py fetches {fetched.group(1)}")


@pytest.mark.parametrize("project, wheel_name", [
    ("css-inline", "css_inline"),
    ("beautifulsoup4", "beautifulsoup4"),
])
def test_desktop_and_browser_render_with_the_same_version(project, wheel_name):
    """The browser build used Pyodide's lockfile copies -- css-inline
    0.16.0 and beautifulsoup4 4.13.3 -- while the desktop pinned other
    versions, so the same Word file could produce different email HTML
    depending on which build made it. Both are now vendored from PyPI
    (css-inline publishes a wheel for this Pyodide ABI), and the same
    three places as python-docx have to agree."""
    reqs = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    vendor = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(
        encoding="utf-8")

    desktop = re.search(rf"^{re.escape(project)}==([\d.]+)", reqs, re.M)
    fetched = re.search(rf'"{wheel_name}-([\d.]+)-[^"/]+\.whl"\s*:', vendor)
    browser = re.search(
        rf'"\./pyodide/(?:[^"/]+/)*{wheel_name}-([\d.]+)-[^"/]+\.whl"', app_js)
    assert desktop and fetched and browser, (
        f"could not find all three pins for {project}: requirements.txt "
        f"{bool(desktop)}, PYPI_WHEELS {bool(fetched)}, PY_PACKAGES {bool(browser)}")
    assert desktop.group(1) == fetched.group(1) == browser.group(1), (
        f"requirements.txt pins {project} {desktop.group(1)}, "
        f"vendor_pyodide.py fetches {fetched.group(1)}, web/app.js loads "
        f"{browser.group(1)}")

    # Loaded by path, so it must not ALSO be requested by lockfile name --
    # that would load Pyodide's older copy alongside, or instead.
    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    names = re.findall(r'"([^"./][^"]*)"', packages.group(1))
    assert wheel_name not in names and project not in names, (
        f"{project} is both vendored from PyPI and requested from the lockfile")
    vendored = re.search(r"^PACKAGES\s*=\s*\((.*?)\)", vendor, re.M | re.S)
    assert project not in re.findall(r'"([^"]+)"', vendored.group(1)), (
        f"{project} is still fetched from the Pyodide lockfile as well")


def test_beautifulsoup4_dependencies_are_requested_by_name():
    """beautifulsoup4 is loaded by path, so -- exactly as with python-docx
    and lxml -- the lockfile resolver never sees its requirements. Its
    dependencies have to be named, or the page boots and then fails on
    `import bs4`."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    vendor = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(
        encoding="utf-8")
    packages = re.search(r"const PY_PACKAGES = \[(.*?)\];", app_js, re.S)
    loaded = set(re.findall(r'"([^"./][^"]*)"', packages.group(1)))
    vendored = re.search(r"^PACKAGES\s*=\s*\((.*?)\)", vendor, re.M | re.S)
    fetched = set(re.findall(r'"([^"]+)"', vendored.group(1)))
    for dependency in ("soupsieve", "typing-extensions"):
        assert dependency in loaded, f"web/app.js does not load {dependency}"
        assert dependency in fetched, f"vendor_pyodide.py does not fetch {dependency}"


def test_vendor_script_refuses_filenames_that_escape_the_vendor_dir():
    """Wheel filenames come out of `pyodide-lock.json`, which is fetched
    from the CDN and is NOT yet hash-verified when they are used -- they
    define the very set that verification then checks. They reach both a
    URL and a write path.

    The deploy path fails closed on its own (a file absent from
    `pyodide-assets.json` trips the "downloaded but not in the hash
    file" check before anything is written), but `--write-hashes` has no
    such backstop by definition, so a tampered lockfile could write
    outside `web/pyodide/` on a maintainer's machine.
    """
    sys.path.insert(0, str(REPO_ROOT / "web"))
    try:
        import vendor_pyodide
    finally:
        sys.path.pop(0)

    for hostile in ("../../.github/workflows/deploy-web.yml",
                    r"..\..\evil.py", "/etc/passwd", "a/b.whl", "..", ""):
        with pytest.raises(ValueError):
            vendor_pyodide._safe_name(hostile)

    # And the real names must still pass, or the guard breaks the deploy.
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    for name in assets["files"]:
        assert vendor_pyodide._safe_name(name) == name


def test_the_downloadable_html_is_the_self_contained_document():
    """Reported from the field: "the preview is working perfectly, but
    when downloading the html the images are gone. They are present when
    I download the email draft though."

    `WebBuildResult` carries two documents. `standalone_html` has the
    photos as `data:` URIs; `html` has them as
    `raw.githubusercontent.com` URLs. The page is hardcoded to CID mode
    and never runs `publish-images`, so those URLs point at files that
    were never uploaded -- every one 404s. The download was wired to
    `html`, which is why the preview looked perfect and the downloaded
    file did not.

    This asserts the wiring in the embedded Python, since that is where
    the mistake was and no unit test of `webapp` could have caught it.
    """
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    block = re.search(r"def _web_build\(.*?\n    return json\.dumps",
                      app_js, re.S)
    assert block, "the _web_build glue was not found in app.js"
    glue = block.group(0)

    write = re.search(
        r'p = out / f"issue-\{int\(issue\)\}\.html"\s*\n\s*'
        r'p\.write_text\((result\.\w+)', glue)
    assert write, "could not find where the .html download is written"
    assert write.group(1) == "result.standalone_html", (
        f"the .html download is written from {write.group(1)}; it must be "
        f"result.standalone_html, or the downloaded file points at photos "
        f"that were never published"
    )


def test_the_mail_html_is_never_offered_as_a_download():
    """The stronger form of the check above: `result.html` must not
    reach the virtual filesystem at all. It is the bytes to validate and
    to hand the mail backend -- handing it to an editor gives them a
    file whose every photo is a dead GitHub URL."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"def _web_build\(.*?\n    return json\.dumps",
                      app_js, re.S)
    glue = re.sub(r"#[^\n]*", "", block.group(0))   # drop comments

    assert not re.search(r"write_text\(\s*result\.html", glue), (
        "result.html is being written to a file the editor can download")


# ---------- preview views + offline support ---------------------------

def test_the_page_exposes_what_the_preview_views_need():
    """The three views are driven by data the build already produces --
    `placeholders` to highlight, `plaintext` for the text/plain view --
    so nothing is recomputed in JavaScript where it could drift from
    what the `.eml` actually carries."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"def _web_build\(.*?\n_web_build", app_js, re.S)
    assert block, "the _web_build glue was not found"
    for field in ('"placeholders": list(result.placeholders)',
                  '"plaintext": result.plaintext'):
        assert field in block.group(0), f"missing from the payload: {field}"


def test_the_plaintext_view_shows_the_bytes_the_eml_carries():
    """`scripts.webapp` must take the plain-text alternative from the
    same converter `scripts.mail.eml` uses. A second conversion would
    let the page show an editor something recipients never receive."""
    webapp = (REPO_ROOT / "scripts" / "webapp.py").read_text(encoding="utf-8")
    assert "_plaintext_alternative(draft.html)" in webapp, (
        "the plain-text view must be derived from the same HTML the "
        ".eml embeds, not merely the same converter")
    assert "from scripts.mail.eml import _plaintext_alternative" in webapp


def test_preview_marks_are_never_written_to_the_downloaded_file():
    """The highlight markup exists to be looked at. Writing it into the
    artefact an editor sends would be far worse than the problem it
    solves, so the marking happens on a parsed copy in memory."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "new DOMParser().parseFromString(lastPreview.html" in app_js, (
        "the preview should be marked on a parsed copy")
    # The Python glue must still write the clean document to disk.
    assert "p.write_text(result.standalone_html" in app_js
    glue = re.search(r"def _web_build\(.*?\n    return json\.dumps",
                     app_js, re.S).group(0)
    assert "meridian-flag" not in glue, (
        "highlight markup is reaching the file that gets downloaded")


def test_placeholder_marking_walks_text_nodes_not_raw_html():
    """A string replace over the HTML would also hit attribute values --
    `alt` text legitimately contains bracketed words -- and injecting a
    tag into an attribute produces broken markup, in the very document
    an editor is inspecting for correctness."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    fn = re.search(r"function flagPlaceholders\(.*?\n\}", app_js, re.S)
    assert fn, "flagPlaceholders not found"
    assert "createTreeWalker" in fn.group(0)
    assert "NodeFilter.SHOW_TEXT" in fn.group(0)


def test_the_service_worker_never_serves_a_stale_bundle():
    """`meridian-bundle.zip` is a copy of the real `scripts/` package.
    Cache-first on that file would mean the page silently runs last
    release's parser -- the exact failure the drift test exists to
    prevent, reintroduced by another route. Only the Pyodide runtime,
    which is version-pinned and hash-verified, may be cache-first."""
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")

    cache_first = re.search(r"if \(isRuntimeAsset\(url\)\).*?\n    return;",
                            sw, re.S)
    assert cache_first, "the cache-first branch was not found"
    assert "meridian-bundle" not in cache_first.group(0)

    guard = re.search(r"function isRuntimeAsset\(url\) \{.*?\n\}", sw, re.S)
    assert guard and "/pyodide/" in guard.group(0)


def test_the_worker_warms_the_runtime_core_the_deploy_vendors():
    """The page asks the worker to cache the core runtime once it has
    booted, because on a first visit those files load before the worker
    takes control. A name the deploy does not vendor fails that
    `cache.add` silently, and offline then works only from the second
    visit. Pyodide 314 renamed `pyodide.asm.js` to `pyodide.asm.mjs`,
    which is how the two lists can drift apart."""
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    sys.path.insert(0, str(REPO_ROOT / "web"))
    try:
        import vendor_pyodide
    finally:
        sys.path.pop(0)

    warmed = re.search(r"const RUNTIME_CORE = \[(.*?)\];", sw, re.S)
    assert warmed, "RUNTIME_CORE not found in web/sw.js"
    names = re.findall(r'"([^"]+)"', warmed.group(1))
    # Bare filenames. Their directory is the Pyodide version, which the
    # page names when it asks; a path here would be one version's.
    assert not any("/" in name for name in names), names
    assert sorted(names) == sorted(vendor_pyodide.CORE_FILES)


def test_the_page_tells_the_worker_which_runtime_to_warm():
    """The worker holds only the core filenames; their directory changes
    with every Pyodide version, and only the page knows which one it
    booted. The directory it names has to be checked before anything is
    fetched into the cache (see the Node test below for the check)."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")

    post = re.search(r"controller\?\.postMessage\(\{(.*?)\}\)", app_js, re.S)
    assert post, "the page no longer asks the worker to warm the runtime"
    assert "indexURL: new URL(PYODIDE_INDEX_URL, location.href).href" in post.group(1)

    handler = re.search(r'self\.addEventListener\("message".*?\n\}\);', sw, re.S)
    assert handler, "the worker's message handler was not found"
    body = handler.group(0)
    check = body.index("runtimeDirectory(event.data.indexURL)")
    assert check < body.index("caches.open"), (
        "the worker opens its cache before checking the directory it was sent")
    assert "if (!directory) return;" in body


_WORKER_DIRECTORY_CHECK = """
const self = { location: new URL(process.argv[2]) };
%s
%s
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(cases.map((value) => {
  const url = runtimeDirectory(value);
  return url === null ? null : url.href;
})));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_the_worker_warms_only_a_version_directory_of_its_own_runtime(tmp_path):
    """Runs `runtimeDirectory` from web/sw.js under Node. Whatever a
    "warm" message names, the worker may only fetch into its cache from
    one directory below its own `./pyodide/` -- never another origin,
    another part of the site, or a URL that normalises its way out."""
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    root_decl = re.search(r"^const RUNTIME_ROOT = .*?;\n", sw, re.M)
    check = re.search(r"^function runtimeDirectory\(value\) \{.*?^\}\n",
                      sw, re.M | re.S)
    assert root_decl and check, "RUNTIME_ROOT / runtimeDirectory not found"
    script = tmp_path / "check.cjs"
    script.write_text(_WORKER_DIRECTORY_CHECK % (root_decl.group(0), check.group(0)),
                      encoding="utf-8")

    root = "https://example.org/meridian/pyodide/"
    accepted = [root + "314.0.7/", root + "0.29.4/", root + "315.0.0a1/"]
    refused = [
        "https://evil.example/meridian/pyodide/314.0.7/",   # another origin
        "http://example.org/meridian/pyodide/314.0.7/",     # another scheme
        "https://example.org/other/pyodide/314.0.7/",       # outside the site
        "https://example.org/meridian/PYODIDE/314.0.7/",
        root,                                               # no version
        root + "314.0.7",                                   # a file, not a directory
        root + "314.0.7/pyodide.js",
        root + "314.0.7/nested/",
        root + "../meridian-bundle.zip",                    # normalises out
        root + "%2e%2e/",
        root + "..%2f/",
        root + ".hidden/",
        root + "314.0.7/?v=2",
        root + "314.0.7/#x",
        "https://user@example.org/meridian/pyodide/314.0.7/",
        "./pyodide/314.0.7/",                               # not absolute
        "javascript:alert(1)//",
        None, 42, {}, [],
    ]
    run = subprocess.run(
        [shutil.which("node"), str(script), "https://example.org/meridian/sw.js"],
        input=json.dumps(accepted + refused), capture_output=True, text=True,
        encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    verdicts = json.loads(run.stdout)
    assert verdicts[:len(accepted)] == accepted
    let_through = [case for case, verdict in zip(refused, verdicts[len(accepted):])
                   if verdict is not None]
    assert not let_through, f"the worker would warm from: {let_through}"


def test_the_service_worker_is_same_origin_only():
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    assert "url.origin !== self.location.origin" in sw
    assert 'request.method !== "GET"' in sw


def test_a_new_deploy_invalidates_every_previous_cache():
    """Without this a released fix could sit behind a cache indefinitely.
    The deploy stamps the commit SHA into sw.js, so its bytes change,
    the browser installs the new worker, and activate drops the rest."""
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    wf = (REPO_ROOT / ".github" / "workflows" / "deploy-web.yml").read_text(
        encoding="utf-8")

    assert "__MERIDIAN_VERSION__" in sw, "the version placeholder is gone"
    assert "__MERIDIAN_VERSION__" in wf, "the deploy no longer stamps it"
    assert "github.sha" in wf
    assert re.search(r"caches\.delete", sw), "old caches are never dropped"
    assert wf.index("__MERIDIAN_VERSION__") < wf.index("upload-pages-artifact")


def test_the_page_never_runs_an_app_js_from_another_deploy():
    """index.html and app.js both name the runtime's directory, so they
    have to come from one deploy. Measured in Chrome against a server
    sending GitHub Pages' `max-age=600`: on the first reload after a
    0.29.4 -> 314.0.7 deploy the browser revalidated the document only,
    and took app.js -- fetched minutes earlier -- from its own cache
    without asking the worker. 314's loader then read 0.29.4's lockfile,
    stdlib and wasm, asked for a `0.29.4/pyodide.asm.mjs` that never
    existed, and the boot failed. With `app.js?v=<commit>` the fresh
    document names a URL no cache holds, and the same reload booted
    314.0.7 from 314.0.7's files alone."""
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    wf = (REPO_ROOT / ".github" / "workflows" / "deploy-web.yml").read_text(
        encoding="utf-8")

    modules = re.findall(r'<script src="([^"]+)" type="module">', html)
    assert modules == ["app.js?v=__MERIDIAN_VERSION__"], modules
    # The deploy stamps the page as well as the worker, before publishing.
    stamp = re.search(r'for name in \(([^)]*)\):', wf)
    assert stamp and {"web/sw.js", "web/index.html"} <= set(
        re.findall(r'"([^"]+)"', stamp.group(1))), "index.html is not stamped"
    assert wf.index('"web/index.html"') < wf.index("upload-pages-artifact")
    # Offline, the page asks for the stamped URL; the shell has to hold it.
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    assert "`./app.js?v=${VERSION}`" in shell
    assert '"./app.js"' not in shell


def test_network_first_means_the_server_not_the_http_cache():
    """GitHub Pages sends `max-age=600`, so a plain `fetch()` returns any
    copy under ten minutes old -- "network first" in name only. Measured
    in Chrome: after a 0.29.4 -> 314.0.7 deploy, a new tab opened within
    ten minutes of a visit got the previous index.html through the worker
    and ran the whole previous release; revalidating, the same tab ran
    314.0.7 from 314.0.7's files."""
    sw = (REPO_ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    network_first = sw[sw.index("if (isRuntimeAsset(url))"):]
    network_first = network_first[network_first.index("    return;"):]
    assert 'fetch(request, { cache: "no-cache" })' in network_first
    assert re.search(r"fetch\(request\)", network_first) is None


def test_the_csp_allows_the_worker_it_registers():
    """`worker-src` governs the service worker script. Registering one
    the policy forbids fails silently in the console -- the page still
    works, so the regression would go unnoticed until someone needed
    offline."""
    html = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', html)
    worker = re.search(r"worker-src ([^;]+)", csp.group(1))
    assert worker and "'self'" in worker.group(1)


def test_the_worker_is_not_registered_on_a_cloned_page():
    """A clone that registers a worker persists itself on the editor's
    machine after the tab closes, turning a phishing page into a
    resident one."""
    app_js = (REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    reg = re.search(r'if \("serviceWorker" in navigator.*?\n\}', app_js, re.S)
    assert reg, "the registration block was not found"
    # `isSecureContext` rather than a protocol check: it is true for
    # https AND for localhost, so the worker is also exercised during
    # local development instead of only ever in production.
    assert "window.isSecureContext" in reg.group(0)
    assert "window.top === window.self" in reg.group(0)
