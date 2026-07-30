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

**What the page fetches, precisely** — the earlier claim of "exactly two
requests" was wrong, and this section is the one place that has to be
accurate:

- `cdn.jsdelivr.net` — the Pyodide loader (pinned with Subresource
  Integrity), plus the assets it then pulls itself: `pyodide.asm.js`,
  `pyodide.asm.wasm`, `python_stdlib.zip`, `pyodide-lock.json`, and the
  wheels for `css_inline`, `jinja2`, `beautifulsoup4` and `lxml`.
- `pypi.org` and `files.pythonhosted.org` — `python-docx` only, which is
  not in Pyodide's distribution. It carries an exact version pin.
- Your own origin — `meridian-bundle.zip`.

A `Content-Security-Policy` in `index.html` restricts `connect-src` to
exactly those hosts and sets `form-action 'none'`, so the "nothing is
uploaded" promise is enforced structurally rather than by intent alone.
The trust anchor is jsDelivr: SRI pins the loader, but the loader
fetches four further files from the same origin, so a compromise of
jsDelivr is not something the hash defends against. Vendoring the
Pyodide distribution next to `web/` and pointing `loadPyodide` at
`./pyodide/` would move that anchor onto your own host, and is the right
next step for an institution that wants the guarantee to be absolute.

The DOCX itself is never sent anywhere — there is no endpoint to send it
to. After the first load the runtime is browser-cached; note there is no
service worker, so this is ordinary HTTP caching, not true offline
support.

## Two things that will bite you

**Refresh the bundle after touching `scripts/`.** The zip is a committed
copy of the toolkit. Edit `scripts/docx_parser.py`, forget to re-run
`build_bundle.py`, and the desktop launcher gets your fix while the web
page silently keeps running the old code. `tests/test_web_bundle.py`
fails the suite when the two diverge — do not skip it.

**Do not bump Pyodide without checking `css_inline`.** The entire email
layout depends on `css_inline`, which is Rust-backed rather than pure
Python, so it only works where a WebAssembly build exists. It ships in
Pyodide's **0.29.x** distribution. The 314.x line moved to ABI `2026_0`
and has no `css_inline` build yet, and the wheel PyPI publishes is
tagged for the older ABI — so bumping the version in `index.html`
breaks the page at install time, with an error that points at micropip
rather than at us. A test pins the version for this reason.

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
