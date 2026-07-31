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
    src = (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(encoding="utf-8")
    assert re.search(r'PYODIDE_VERSION = "0\.29\.\d+"', src), (
        "Pyodide must stay pinned to the 0.29.x line until css_inline "
        "publishes a build for the newer ABI."
    )
    # The script and the hash file must agree, or the deploy fetches one
    # version and checks it against another. That fails closed, but only
    # after someone has already pushed to main.
    assets = json.loads(
        (REPO_ROOT / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    pinned = re.search(r'PYODIDE_VERSION = "([^"]+)"', src).group(1)
    assert assets["pyodide_version"] == pinned


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
    assert "./pyodide/pyodide.js" in tags

    # Without an explicit indexURL the loader falls back to the CDN for
    # the wasm, the stdlib and every wheel -- the <script> tag alone
    # moves only 18.5 KB of the 16 MB.
    assert "loadPyodide({ indexURL: PYODIDE_INDEX_URL })" in app_js
    assert re.search(r'PYODIDE_INDEX_URL = "\./pyodide/"', app_js)


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
        r'"\./pyodide/python_docx-([\d.]+)-py3-none-any\.whl"', app_js)
    assert desktop and browser and fetched, "could not find all three pins"
    assert desktop.group(1) == browser.group(1) == fetched.group(1), (
        f"requirements.txt pins {desktop.group(1)}, web/app.js loads "
        f"{browser.group(1)}, vendor_pyodide.py fetches {fetched.group(1)}")


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
                    "..\..\evil.py", "/etc/passwd", "a/b.whl", "..", ""):
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
    assert "_plaintext_alternative(final_html)" in webapp
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
