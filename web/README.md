# MERIDIAN in the browser

A static page that turns a filled `issue-N.docx` into a ready-to-send
email draft, with **no server, no install, and no upload**. The Word
file is read, parsed, rendered and drafted inside the browser tab; the
editor gets back a `.eml` they double-click.

It exists for editors who cannot run the desktop launcher — a locked-down
university machine where installing Python is the actual barrier, or a
stand-in editor covering one issue who should not have to set up a
toolkit to do it.

## How it works

The page runs **the real `scripts/` package** inside
[Pyodide](https://pyodide.org) (CPython compiled to WebAssembly). There
is no second, JavaScript implementation of the pipeline to drift out of
sync — `web/app.js` contains no newsletter logic at all. It boots
Pyodide, unpacks `meridian-bundle.zip` into the virtual filesystem, and
calls `scripts.webapp.build_from_bytes`.

```text
web/index.html            markup
web/style.css             app chrome (NU blue / gold, light + dark)
web/app.js                boot, file handling, results — no pipeline logic
web/build_bundle.py       packs scripts/ templates/ locales/ images/
web/meridian-bundle.zip   committed output of the above (~230 KB)
```

## Deploying

**This repository deploys automatically.**
`.github/workflows/deploy-web.yml` publishes **only** this directory to
GitHub Pages on every push to `main` that touches `web/`, `scripts/`,
`templates/`, `locales/` or `images/`. The live page is:

<https://basilechretien.github.io/Newsletter-graduate-school-medicine/>

Two deliberate properties of that workflow:

- **Only `web/` is served.** Pages-from-branch-root would expose the
  whole tree and push the page down to `/web/`.
- **The deploy is gated on `build_bundle.py --verify`.** If someone edits
  the toolkit and forgets to refresh the bundle, the deploy *fails* and
  the live site stays on the last good version, rather than quietly
  serving code a release behind the desktop launcher.

Pages must be set to build from **GitHub Actions** (not from a branch)
for this to work — repository Settings → Pages → Source.

Forking to another institution? Any static host works; the only
requirement is an HTTP origin, because the page `fetch`es its bundle and
`file://` will not do. Nothing needs configuring and there is no secret
to store.

**What the page fetches, precisely** — an earlier version of this
section claimed "exactly two requests" and was wrong, so this is the one
place that has to stay accurate:

- **Your own origin, and nothing else.** `index.html`, `app.js` (as
  `app.js?v=<commit>`), `style.css`, `meridian-bundle.zip`, and
  `./pyodide/<version>/` — the whole runtime, in a directory named for
  the Pyodide version: `pyodide.js`, `pyodide.asm.mjs`, `pyodide.asm.wasm`,
  `python_stdlib.zip`, `pyodide-lock.json`, and the wheels for
  `css_inline`, `jinja2` (with `markupsafe`), `beautifulsoup4` (with
  `soupsieve` and `typing-extensions`), `lxml`, `pillow` and
  `python-docx`.

No CDN, no PyPI, no third party. That is what lets the
`Content-Security-Policy` in `index.html` set `script-src 'self'
'wasm-unsafe-eval'` and `connect-src 'self'`, alongside `form-action
'none'` and `default-src 'none'`.

It used to be otherwise, and the reason for the change is worth
recording. The page loaded ~10 MB from `cdn.jsdelivr.net`, which serves
`/npm/<any-package>` and `/gh/<any-user>/<any-repo>` from that same
host — so `script-src https://cdn.jsdelivr.net` admitted any JavaScript
an attacker could publish to npm or tag on GitHub. That was verified
against the live site: an arbitrary npm package and an arbitrary GitHub
repository both loaded and executed. Subresource Integrity did not close
it either, because SRI covered only the 18.5 KB loader; the wasm, the
stdlib and every wheel it then fetched were unchecked — roughly 99.8% of
the executed bytes, on a page that reads unpublished institutional
documents.

Be precise about what the current policy buys, all the same: the
application has **no upload endpoint** and every step runs locally, and
the CSP narrows where any script *could* send data. CSP has no
`navigate-to` directive in shipping browsers, so `window.open` and
`location` remain outside it. The local-only guarantee rests on the code
and its dependencies; the policy is defence-in-depth on top of that, not
a proof.

**The runtime is fetched at deploy time, not committed.** ~16 MB against
a 5.5 MB repository — and the README tells editors to download that
repository as a ZIP, so committing it would nearly triple the download
for the desktop workflow in order to benefit the browser one. Instead
`.github/workflows/deploy-web.yml` runs `python web/vendor_pyodide.py`
before publishing, which downloads every file and checks it against the
SHA-256 hashes in `web/pyodide-assets.json`. That file **is** committed
and reviewable, so tampering is detectable even though the payload is
not in git history; a mismatch fails the deploy and the live site stays
on the last good version. To run the page locally, run the same script
once, then serve `web/` over HTTP.

**Every file has two sources.** `vendor_pyodide.py` tries each file's
upstream first -- jsDelivr for the runtime and the lockfile's wheels, PyPI
for the wheels vendored from there -- and then a permanent mirror: the
assets of this repository's pre-release `pyodide-runtime-<version>`,
published by `.github/workflows/mirror-runtime.yml` whenever the hash file
changes. jsDelivr's `/pyodide/` path carries no retention promise, and
this runtime is meant to stay pinned for years; without the mirror, a file
disappearing upstream would stop every deploy and freeze the live site.
The hash file alone decides which bytes are accepted, from either source.
A fork sets `MERIDIAN_RUNTIME_MIRROR` to its own copy.

Serving from your own origin has a second benefit worth noting for a
hospital: the page works on institutional networks that block public
CDNs outright.

The DOCX itself is never sent anywhere — there is no endpoint to send it
to. After the first load the runtime is cached by a service worker
(`web/sw.js`), so the page also runs offline; see that file for why the
runtime is cache-first but `meridian-bundle.zip` is network-first.

**No cache can answer for another release.** The runtime's own filenames
are the same in every Pyodide version, and on the first visit after a
deploy the previous service worker is still in charge, with the previous
runtime in its cache. So each version is served from its own directory,
`./pyodide/<version>/`, which no cache has seen. `index.html` and
`app.js` both name that directory, so they must come from the same
deploy: `index.html` loads `app.js?v=<commit>` (the deploy stamps it, as
it stamps `sw.js`), and the worker's network-first requests revalidate
instead of taking the browser's copy, which GitHub Pages lets live ten
minutes. Each was measured in Chrome, upgrading 0.29.4 to 314.0.7 against
a server sending GitHub Pages' headers. Without the directory, the new
`app.js` booted 0.29.4 from the worker's cache. Without the stamp, a
reload paired the new `index.html` with the old `app.js` (the browser
reuses it without asking the worker), and 314.0.7's loader read 0.29.4's
files and failed to boot. Without revalidation, a new tab opened within
ten minutes ran the whole previous release.

## Things that will bite you

**Refresh the bundle after touching `scripts/`.** The zip is a committed
copy of the toolkit. Edit `scripts/docx_parser.py`, forget to re-run
`build_bundle.py`, and the desktop launcher gets your fix while the web
page silently keeps running the old code. `tests/test_web_bundle.py`
fails the suite when the two diverge — do not skip it.

**Do not bump Pyodide without checking `css_inline`.** The entire email
layout depends on `css_inline`, which is Rust-backed rather than pure
Python, so it only works where a WebAssembly build exists for the
runtime's ABI. The page runs Pyodide **314.x** (ABI `pyemscripten_2026_0`)
with css-inline's own PyPI wheel for that ABI, which it publishes from
0.21.3 on. Pyodide changes ABI about once a year, and a runtime paired
with a wheel built for another line breaks the page at install time, with
an error that points at the loader rather than at us. The weekly update
report says when a newer Pyodide can run the page. Then: bump
`PYODIDE_VERSION` in `web/vendor_pyodide.py`; move every
`./pyodide/<version>/` in `index.html` and `app.js` to the new version (a
test names any that lag); switch the css-inline wheel to its build for
the new ABI in `PYPI_WHEELS` and in `PY_PACKAGES` in `app.js`; check the
runtime's own filenames against the new release (314 renamed
`pyodide.asm.js` to `pyodide.asm.mjs`), which `CORE_FILES` and
`RUNTIME_CORE` in `sw.js` list; re-run the script with `--write-hashes`,
commit the new `pyodide-assets.json`, and let the `web-engine` workflow
compare the result with the desktop build. Tests check that the script,
the hash file and the page's paths agree and that every compiled wheel is
built for one ABI. The script writes the runtime to
`web/pyodide/<version>/` and removes anything else under `web/pyodide/`.
If a wheel fails to load, after a partial deploy for instance, the page
stops at boot with "could not start" rather than running without it:
`loadPackage` does not throw on a failed wheel, so `app.js` collects its
`errorCallback` messages and throws. Without that, a missing Pillow wheel
gave full-size photos under "Ready to send", since the toolkit treats
Pillow as optional.

**Keep the vendored wheels at the desktop's versions.** `css-inline`,
`beautifulsoup4` and `python-docx` are each pinned in three places:
`requirements.txt`, `PYPI_WHEELS` in `vendor_pyodide.py`, and
`PY_PACKAGES` in `app.js`. A Dependabot bump of `requirements.txt` alone
fails `tests/test_web_bundle.py` on purpose, with the steps to finish it.
`jinja2`, `lxml` and `pillow` come from Pyodide's lockfile instead, so
they move only with Pyodide: 314.0.7 ships Pillow 12.2.0 against the
desktop's 12.3.0, because Pillow publishes no WebAssembly wheel on PyPI.

## Testing the real engine

`tests/test_web_engine.py` runs this page's engine under Node -- the
vendored runtime, the packages `app.js` loads and the committed bundle --
and checks it builds the same email as the desktop toolkit, for the Word
template and a small fixture. The `web-engine` workflow runs it on every
relevant change and weekly, which also catches a runtime that can no
longer be fetched before a deploy needs it. Locally:

```bash
python web/vendor_pyodide.py
MERIDIAN_WEB_ENGINE=1 python -m pytest tests/test_web_engine.py
```

It compares against the Python you run it with, so install
`requirements.txt` first: an older desktop css-inline is a real mismatch.

It compares the email's HTML and text, not its photos, and that is
deliberate: a JPEG the toolkit re-encodes comes out with different bytes
in the browser whatever the Pillow versions, because Pyodide's Pillow
encodes with libjpeg 9 and the desktop wheels with libjpeg-turbo. On a
real issue, desktop Pillow 11.3.0, 12.2.0 and 12.3.0 all gave one set of
bytes and the browser's 11.3.0 and 12.2.0 another, 945 B apart on a
146 KB photo.

## Deliberate limits

- **`.eml`, not "send".** The page never sends mail. It hands back a
  draft; the editor reviews it and presses Send in their own client
  from their own address. A browser page has no business holding
  credentials for a university mail server.
- **Hosted-photo mode is not offered here at all.** The page always
  embeds. Two reasons: the page cannot push to GitHub, so the URLs would
  point at files that were never published; and inside Pyodide there is
  no env var and no `git`, so `get_default_repo()` always resolves to
  the UPSTREAM repository -- a fork would email photos pointing at
  someone else's repo, at paths that exist only in their own.
  `scripts.webapp.build_from_bytes` still supports `image_mode="url"`
  for a server or notebook caller that genuinely can publish.
- **BCC stays local.** Addresses typed into the page are written only
  into the `.eml` the editor downloads. They are never transmitted —
  there is nowhere to transmit them to.
- **Outlook opens `.eml` as a draft; Apple Mail does not.** Apple Mail
  shows a read-only viewer, so macOS editors are better served by the
  desktop launcher until that path is addressed.

## Developing locally

```bash
python -m http.server 8765 --directory web
```

Then open <http://localhost:8765>. Opening `index.html` from the
filesystem will not work — `fetch` of the bundle needs an HTTP origin.
