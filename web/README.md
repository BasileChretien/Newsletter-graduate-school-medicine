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

Any static host works. For GitHub Pages:

1. Refresh the bundle and commit it:

```bash
python web/build_bundle.py
```

2. Enable Pages for the repository, serving the `web/` directory (or
   copy `web/` to a `gh-pages` branch).

There is nothing to configure and no secret to store. The page makes
exactly two network requests, both to public CDNs: the Pyodide runtime
and the Python wheels. After the first load both are browser-cached and
the page works offline.

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
- **Hosted-photo mode is offered but not recommended here.** It needs
  the photos pushed to GitHub before recipients open the mail, and the
  page cannot push. Embedding photos in the `.eml` is the default and
  needs no publishing step at all.
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
