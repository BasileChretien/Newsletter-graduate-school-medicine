# Changelog

All notable changes to MERIDIAN are documented here.

The toolkit follows [Semantic Versioning](https://semver.org). The detailed
per-bundle commit history (29 fix bundles across 10 specialist-review rounds)
is preserved in `git log` for archaeology.

## [Unreleased]

### Fixed — photos in a redirected output folder (MEDIUM)
- **Drop-folder photos crashed `--output-dir`.** They are copied beside
  the redirected output, but their links were still worked out from the
  toolkit folder, so the build stopped on `ValueError: Asset ... must be
  inside repo`. Embedded photos had the same bug, fixed in v1.3.0 (#6);
  drop-folder photos now take the same route. `--output-dir` is also what
  a run falls back to when the toolkit folder is read-only, as in the
  macOS Downloads folder.
- **URL mode opened a draft of broken images.** Hosted photos can only be
  published from the toolkit's own `assets/` folder. With the photos saved
  anywhere else, `all` printed a yellow note and opened the draft anyway,
  and `compose` did not check at all: every recipient would have seen
  broken images. Both now stop before anything is published or opened,
  say why, and say what to do -- move the toolkit folder somewhere
  writable, or use `--backend=eml` to put the photos inside the email. The
  check reads the email itself, so a run whose email shows none of the
  issue's photos is not stopped -- not even with old photos left in the
  folder by an earlier build -- and `--output-dir` set to the toolkit
  folder itself now publishes normally.
- Ported from work left uncommitted in a worktree since 2026-07-29, and
  pinned by nine new tests in `tests/test_output_dir.py`. The website is
  unaffected: it always puts the photos inside the email.

## [v1.5.0] — the website is built to last (2026-09-14)

The website renders with the desktop's libraries, keeps a permanent copy of
its runtime and has its real engine tested every week; the Windows launcher
runs again; photos get real alt text. Python 3.11 is now the minimum for the
desktop launchers — the website is unaffected. **669 tests passing** on
Linux, macOS and Windows.

### Fixed — the Windows launcher stopped right after its banner (HIGH)
- `Make Newsletter.bat` aborted with ". was unexpected at this time."
  on every run, for every Windows editor, from the Phase 2 launcher
  (2026-04-30) on. Friendly sentences in `echo` lines inside `if (...)`
  blocks contained `)`, and cmd.exe reads a block whole: an unescaped
  `)` ends it early wherever it appears. It went unnoticed because
  editors had moved to the website. Found in review.
- The six sentences are reworded without parentheses. One of them had
  not crashed but silently moved the line after it out of its block.
- `tests/test_launcher_bat.py` checks every block, and CI's Windows job
  now runs the real launcher, in a folder that is not a git checkout,
  up to its first prompt.

### Changed — Python 3.11 is now the minimum
- **Python 3.10 reaches end of life on 2026-10-31**, which the weekly
  update check reported (issue #18). `requires-python` in `pyproject.toml`
  and both READMEs now say 3.11+. CI stays on 3.12 and the browser build
  on Pyodide's 3.13, so neither changes.
- **The launchers check the version first.** They install
  `requirements.txt`, which pip reads without `pyproject.toml`, so on an
  older Python the build would stop on a traceback. An editor with only
  Python 3.10 is now told which version the computer has and to install a
  current Python from <https://www.python.org/downloads/>, then re-run.
  `tests/test_python_floor.py` keeps both launchers, both READMEs and
  `requires-python` in step.
- **The `tomli` backport is gone** from `requirements.txt`: 3.11 ships
  `tomllib`, which `scripts/i18n.py` now imports directly.

### Changed — the website is built to last
- **The browser build renders with the desktop's library versions.** It
  used Pyodide's own copies of css-inline (0.16.0) and beautifulsoup4
  (4.13.3) while the desktop pinned 0.21.2 and 4.15.0. Both are now
  vendored from PyPI -- css-inline publishes a wheel for this runtime's
  ABI -- and a test keeps `requirements.txt`, `web/vendor_pyodide.py` and
  `web/app.js` in step, as it already did for python-docx.
- **The runtime can no longer disappear from under the site.** Every file
  `web/vendor_pyodide.py` fetches has a second source: a permanent mirror,
  published as the assets of a pre-release in this repository
  (`pyodide-runtime-<version>`, `.github/workflows/mirror-runtime.yml`).
  jsDelivr's Pyodide path carries no retention promise; the committed
  hashes still decide which bytes are accepted, from either source.
- **The website's real engine is tested.** `.github/workflows/web-engine.yml`
  runs the vendored runtime, the packages the page loads and the committed
  bundle under Node, and checks they build the same email as the desktop,
  for the Word template and a fixture -- on every relevant change and
  weekly, which also catches a runtime that can no longer be fetched.
- **The weekly update report understands compiled wheels.** A newer
  css-inline is offered only once it ships a wheel for the page's Pyodide
  ABI, and a newer Pyodide is reported as usable only once every compiled
  wheel exists for its ABI. css-inline has no Pyodide 314 build yet;
  requested upstream in Stranger6667/css-inline#786.
- Still open, and reported weekly: the browser build's lxml (6.0.2) stays
  below the desktop's 6.1.3 floor until the site can move to Pyodide 314.
  In the browser it parses only the editor's own Word file, in the
  editor's own tab.

### Fixed — photos had meaningless alt text (MEDIUM)
- **Photos went out with alt text like `Picture 122515128`**: what a
  recipient sees when images are blocked, and what a screen reader reads
  aloud. In a real issue none of the 8 pictures had a description, and
  6 of the 7 photos in the email were labelled that way. With no
  description the parser fell back to the picture's object name, which
  Word makes up. It also never read `wp:docPr@descr`, where Word's Alt
  Text box writes, so even a description an editor did type could be
  ignored.
- **The rule now:** a description from Word wins (`wp:docPr`, then
  `pic:cNvPr`), and an object name is never used. A photo without a
  description takes the title of its section. When a section has several
  such photos they are numbered in document order: "Research & Academic
  Updates (1)", "(2)", "(3)". Photos in bullets and in table cells (the
  Featured Highlights cards) are covered too. A Word file without
  numbered sections uses the nearest Word heading above each photo.
- **Decorative images stay silent:** a picture marked decorative in Word
  keeps `alt=""`.
- **The dean's photo still reads "Dean of the Graduate School of
  Medicine".** Before, the renderer rewrote a file name that had been
  passed through as alt text. Now the parser writes the alt text itself,
  recognising the photo by the name the template builder gives it.
  Pinned by `tests/test_photo_alt_text.py`.

## [v1.4.2] — dependencies are checked automatically (2026-09-14)

Maintenance tooling only; the newsletter output is unchanged. **616 tests
passing** on Linux, macOS and Windows.

### Added — dependencies and runtimes are checked automatically
- **Dependabot** (`.github/dependabot.yml`) opens weekly, grouped pull
  requests for `requirements*.txt` and for the GitHub Actions the
  workflows use; CI tests each one on Linux, macOS and Windows. Coupled
  pins fail on purpose: bumping `python-docx` alone fails the existing
  browser-parity test, which says how to finish the job.
- **A weekly report** (`.github/workflows/update-check.yml`, running
  `tools/check_updates.py`) covers what Dependabot cannot see, and keeps
  ONE issue labelled `dependencies` current — opened or updated while
  something needs attention, closed once everything is current:
  - the Pyodide runtime, and whether a newer release still ships every
    package the page loads — `css-inline` above all;
  - the browser build's package versions against `requirements.txt`;
  - the wheel vendored straight from PyPI (`python-docx`);
  - the `requires-python` floor and the CI Python against end-of-life.
- Its first run (issue #18) found real drift: the browser build ships `lxml` 6.0.2,
  below the desktop's 6.1.0 security floor, and different `css-inline`
  and `beautifulsoup4` versions from the desktop; Python 3.10, the
  `requires-python` floor, reaches end of life on 2026-10-31; and
  Pyodide 314.0.7 still lacks `css-inline`, so the page stays on 0.29.4.
- **The READMEs' test counts are checked in CI** (`tools/readme_figures.py`,
  `tests/test_readme_figures.py`): a pull request that adds tests without
  updating the badge and the "Under the hood" figures fails, and
  `python tools/readme_figures.py --fix` rewrites them after a green run.
  The check once read its own test ids as the summary (553 for a suite of
  602); it now reads only the final summary line and refuses a
  collection with errors.

## [v1.4.1] — README refresh (2026-09-14)

Documentation only; no code changes. **551 tests passing** on Linux,
macOS and Windows.

### Changed — README badges and figures
- **Badges** (#14): a new first badge links to the browser builder; the
  test count reads 551 passing (was 378); Python reads 3.10+, the floor
  `pyproject.toml` enforces (CI runs 3.12); the release badge's label no
  longer says v1.0.1, and `README.ja.md` gains that badge.
- **"Under the hood"** (#15): 551 passing tests across 32 files (was 378
  across 28); Python 3.10+; the 29 fix bundles and 10 review rounds dated
  "up to v1.0.1". The paragraph now links the latest release instead of
  naming a version, so it no longer goes stale with every tag.

## [v1.4.0] — the email keeps Word's alignment (2026-09-14)

One HIGH fix from a field report — justified text came out
ragged-right — extended at the maintainer's request to alignment set by
table styles; and the README now opens with the website. **551 tests
passing** on Linux, macOS and Windows.

### Fixed — justified and centred text came out left-aligned (HIGH)
- **Reported from the field.** Word's paragraph alignment (`w:jc`) was
  never read: `paragraph_to_html` handled runs, links and pictures, so
  every paragraph fell back to the stylesheet's left alignment. The issue
  that exposed it had 106 of its 125 paragraphs justified (両端揃え, the
  default when Word is set up for Japanese) and its photo captions
  centred.
- Alignment is now resolved the way Word does — direct formatting, then
  the paragraph style and its `basedOn` chain, then the document
  defaults — and carried on body paragraphs, bullet items and table cells
  (data tables, highlight cards, layout tables). Measured on that issue:
  23 body paragraphs, 11 table cells and 5 centred paragraphs now match
  Word, for +748 bytes (42.9 → 43.6 KB).
- Only `justify`, `center` and `right` are ever written. Word's values go
  through an allowlist in the parser and again in the renderer, because
  they land in a `style` attribute, where autoescaping does not stop a
  `;`. Left and unset write nothing, so a document without alignment
  renders exactly as before.
- A photo in a centred or right-aligned paragraph now moves with it.
  Photos are `display:block`, which `text-align` does not move in Gmail
  or Apple Mail, so they also get auto margins; Outlook ignores those
  margins and follows the paragraph's `text-align` instead.
- Table styles are honoured too: a table style's own alignment, and its
  conditional formatting — header row, total row, first and last column,
  row and column banding, corner cells — as each table switches it on
  with `w:tblLook`. Where Word and ECMA-376 disagree (a header row beats
  the first column where they meet; a missing band size means no banding;
  a table without `w:tblLook` gets header row and first column), this
  follows Word as Microsoft documents it in [MS-OI29500], including the
  `overrideTableStyleFontSizeAndJustification` rule for documents from
  before Word 2013. No current issue uses a table style, so none of their
  output changes.
- Styles are resolved once per document. Walking style chains for every
  table cell made the 20,000-cell table cap six times slower to parse
  (0.85 s → 5.1 s); it now takes 1.26 s. That matters most in the
  browser, where Python runs several times slower.
- A table cell whose paragraphs disagree (a centred line above justified
  text, say) keeps the default rather than guessing. Section headings,
  sub-headings and the masthead keep the fixed MERIDIAN design.
- In the bundled template, the copyright line and the dean's name block
  are centred in Word and are now centred in the email too.

### Changed — the README starts with the website
- `README.md` and `README.ja.md` open with the browser builder: how to
  use it step by step, and where the photos are stored — the Word file,
  the browser tab's memory during the build, the downloaded `.eml` and
  `.html`, then Sent Items and recipients' mailboxes; never online. The
  desktop launcher's documentation follows, unchanged, as the backup
  route. The repository's About link now points at the website.
- `web/README.md` no longer says the page has no service worker; v1.3.0
  added one.

## [v1.3.0] — see it the way recipients will (2026-08-03)

Four HIGH fixes, three new preview capabilities, offline support and a
restyled builder page. Two of the fixes came from field reports — "when
downloading the html the images are gone" and "[date] is not highlighted
in the preview"; the rest were found while investigating those, and the
restyle was requested separately. **468 tests passing** on Linux, macOS
and Windows.

### Fixed — the downloaded HTML had no photos (HIGH)
- **Reported from the field.** `WebBuildResult` carries two documents:
  `standalone_html`, with photos as `data:` URIs, and `html`, with them
  as `raw.githubusercontent.com` URLs. The browser build is hardcoded to
  CID mode and never runs `publish-images`, so those URLs point at files
  that were never uploaded — every one 404s. The download link was wired
  to `html`, which is exactly why the preview looked perfect, the `.eml`
  was fine, and only the downloaded file was empty.
- Second-order problem worth recording: that file did not merely show
  gaps, it pointed at a public GitHub path for an *unpublished* issue,
  so opening or forwarding it made requests describing an unsent
  newsletter.
- `preview_html` is renamed `standalone_html`, because the old name
  caused this: it read as preview-only scaffolding, so wiring the
  download to `html` looked correct.

### Fixed — the desktop `preview` had the same defect (HIGH)
- `preview` opened `dist/issue-N.html`, which is that same
  unpublished-URL document, so every photo was broken there too.
- **The fix is a second file, deliberately not a change to the first.**
  `compose` reads `dist/issue-N.html` to build the message, and CID mode
  works by rewriting exactly those URLs into `cid:` references. Putting
  `data:` URIs there would have been the obvious-looking fix and a far
  worse bug — Outlook and Gmail strip them, so every recipient would
  have received a newsletter with **no photos at all**. A test asserts
  that file never contains `data:`, named so nobody merges the two.
- `build` now also writes `dist/issue-N.preview.html`, shared with the
  browser build through `scripts/standalone.py` so both surfaces produce
  the same document from the same code.

### Fixed — `--output-dir` crashed on any DOCX with a photo (HIGH)
- `to_raw_url` resolved against `PROJECT_ROOT` while `--output-dir` puts
  the extracted photos beside that directory, raising a bare
  `ValueError` traceback. Every real newsletter has photos — and that
  flag exists for the macOS unwritable-folder case, where the automatic
  `~/Documents/Meridian-Newsletter` fallback takes the same path. **The
  v1.1.2 fix for that production failure could not survive a photo.**

### Fixed — lowercase placeholders were never reported (HIGH)
- `PLACEHOLDER_RE` was `\[[A-Z][^\[\]]{1,60}\]`, carrying two defects:
  the uppercase requirement hid `[date]`, `[handle]` and
  `[inquiry@…]`, and `[A-Z]` plus `{1,60}` demanded two characters
  inside, hiding `[X]`. **Nine unfilled placeholders in the shipped
  template went unreported** — no reminder, and no highlight.
- Not cosmetic: for as long as the reminder has existed it has been
  undercounting, so an issue containing `[date]` could be sent with the
  toolkit reporting nothing wrong.
- The replacement requires at least one *letter* rather than a case.
  That is what keeps numbered citations (`[1]`, `[2023]`, `[1-3]`)
  unflagged — otherwise a reference list buries the real placeholders.
  Any Unicode letter, so a future `[日付]` is caught.
- The masthead hard-block is left **case-sensitive on purpose**, and now
  says so. Relaxing it the same way collides with the template's body
  placeholder `[Month–Month Year]` and hard-blocks a correctly filled
  newsletter — worse than the gap it closes.

### Added — see it the way recipients will
- **Validation problems are highlighted in the preview**, with a count.
  The marking walks text nodes through a parsed copy rather than string-
  replacing the HTML, which would also hit attribute values (`alt` text
  legitimately contains bracketed words) and produce broken markup in
  the document being inspected for correctness. The marks never reach
  the downloaded file or the `.eml`.
- **A "how recipients see it" switch.** *Images blocked* — Outlook
  blocks external images by default, and a newsletter that only makes
  sense with photos reads as blank to those recipients; each photo
  becomes the box a client shows, carrying its alt text. *Plain text* —
  the `text/plain` part, from the same converter **and the same HTML**
  the `.eml` embeds, so it is the bytes recipients get. It immediately
  surfaced a real defect in the current issue: `Nagoya University08/2026`,
  a missing separator invisible in the HTML.

### Added — offline support
- A cold load fetches ~16 MB, and the page could not run at all offline
  or behind a network blocking the host — the locked-down hospital PC
  the browser build exists for. **Measured: 5 s first load, 848 ms fully
  offline.**
- The caching split is the load-bearing decision. `./pyodide/*` is
  cache-first (version-pinned, SHA-256 verified); **everything else,
  including `meridian-bundle.zip`, is network-first** with a cache
  fallback. The bundle is a copy of the real `scripts/` package, so
  serving a stale one means silently running last release's parser — the
  failure the drift test exists to prevent, reintroduced by another
  route.
- The core runtime is warmed after a successful boot, not during
  `install`: those files are fetched by `loadPyodide` before a
  first-visit worker takes control, so offline would otherwise have
  worked only from the *second* visit.
- A partial precache must not activate. `install` originally swallowed
  cache failures and called `skipWaiting()` anyway — and since
  `activate` deletes the previous cache, a connection lost mid-update
  would have destroyed a working offline copy while installing an
  incomplete one.
- The deploy stamps the commit SHA into `sw.js`, so a release changes
  its bytes and every previous cache is dropped. Registration is gated
  on `isSecureContext` and on not being framed: a clone that registers a
  worker persists itself after the tab closes.

### Changed — the builder page looks current
- Restyled the **tool**; `templates/styles.css` styles the newsletter
  and is fixed by the NU guideline, untouched. Brand tokens unchanged —
  NU blue, the gold masthead rule, Cambria, Calibri. Depth instead of
  hairline borders, fluid type via `clamp()` with a floor *and* ceiling,
  the summary as scannable stat tiles, a real dropzone drag state, and
  step 1 turning brand gold on file select via `:has()`.
- Contrast computed from the token values across nine pairs in both
  schemes: worst 5.13:1 light, 7.14:1 dark against AA's 4.5.
  `prefers-reduced-motion` blankets every transition but keeps the
  spinner turning slowly, because a frozen spinner reads as a hung app.

### Fixed — smaller things found along the way
- The empty-DOCX failure path was the one path that returned *without*
  clearing stale output, so an editor whose file came through empty kept
  last quarter's HTML in `dist/`.
- A failed standalone write left a stale `issue-N.preview.html`, which
  `preview` prefers — it would have shown last issue as this build.
- `build_bundle.py` uses `git ls-files`, so a new module that is not yet
  `git add`ed is silently omitted from the bundle. `scripts/standalone.py`
  was, and the page died at boot with `ModuleNotFoundError` — caught
  only by loading the real page in a browser.

## [v1.2.0] — `.eml` export, browser build, self-hosted runtime (2026-07-31)

Two new capabilities, the field-trial photo bug, and the fixes that fell
out of five specialist reviews (security ×2, Python, architecture,
frontend) and four CodeRabbit passes.
**+140 regression tests — 430 passed, 2 skipped, on Linux, macOS and
Windows.**

### Fixed — photos silently dropped by Track Changes (HIGH)
- **Reported from a field trial: "the dean picture is not always loading,
  and the big pictures are not detected."** Root cause was Track Changes.
  `paragraph_to_html` walked only direct `w:r` children, so anything
  inside a `<w:ins>` wrapper — content inserted with Track Changes on and
  never accepted — was never seen. In the reported document that was the
  dean photo and one 550 KB section photo: 2 of 4 images rendered, and
  which ones depended on whether the edit had happened to be accepted.
  Now 4 of 4.
- **Text inserted the same way vanished just as quietly**, which is the
  more dangerous form of this bug: a missing photo is visible in the
  draft, a missing sentence is not. Worth knowing for past issues sent
  before this fix.
- Deletions stay excluded, now by decision rather than by side effect:
  `w:del` and `w:moveFrom` content is skipped explicitly, because
  publishing a struck-out sentence to ~50 people is worse than dropping
  it. Pinned by a test at 50 levels of nesting.

### Changed — the browser build serves its own runtime (HIGH, security)
- **The page loaded ~10 MB of executed code from `cdn.jsdelivr.net`.**
  Two problems, both demonstrated against the live site: jsDelivr also
  serves `/npm/<any-package>` and `/gh/<any-user>/<any-repo>` from that
  host, so `script-src https://cdn.jsdelivr.net` admitted any JavaScript
  an attacker could publish to npm or tag on GitHub (verified — an
  arbitrary npm package and an arbitrary GitHub repo both executed on the
  page); and Subresource Integrity covered only the 18.5 KB loader, so
  the wasm, the stdlib, the lockfile and every wheel it then fetched were
  unchecked — roughly 99.8% of the executed bytes, on a page holding an
  unpublished newsletter and a ~50-address recipient list.
- `web/vendor_pyodide.py` now fetches the whole runtime at deploy time
  and verifies every byte against SHA-256 hashes in the committed
  `web/pyodide-assets.json`. A mismatch fails the deploy and the live
  site stays on the last good version. The ~16 MB payload is **not**
  committed: that is nearly three times the size of the 5.5 MB
  repository on its own, and the README tells editors to download that
  repository as a ZIP — so committing it would roughly *quadruple* what
  the desktop workflow downloads, to benefit the browser one.
- CSP narrows to `default-src 'none'`, `script-src 'self'
  'wasm-unsafe-eval'`, `connect-src 'self'`, `form-action 'none'`.
  micropip — which reached PyPI on every cold load — is gone entirely.
- Side benefit: the page now works on institutional networks that block
  public CDNs outright.
- Honest limit, stated because an earlier round overclaimed here twice:
  CSP has no `navigate-to` directive in shipping browsers, so
  `window.open` and `location` remain outside it. The local-only
  guarantee rests on the code; the policy is defence in depth on top.

### Fixed — crafted-DOCX hardening (HIGH)
- URL-scheme allowlist on hyperlinks (`is_safe_url_scheme`), shared by
  the parser and validator. An unsafe scheme keeps its label and loses
  its href — the marker carries no href at all, so an attacker's URL is
  never echoed into the email.
- DOCX table geometry bounded. `_row_cells` reads a row's own `tc`
  elements rather than `_Row.cells`, avoiding both `gridSpan` expansion
  (a 64-column row with large spans could amplify to millions of cells)
  and `_tc_above` recursion (a ~3000-deep `w:vMerge` chain raised
  `RecursionError`). Both are reached from `_extract_masthead`, which
  runs on *every* document before any parsing decision.
- `MAX_TABLE_CELLS_TOTAL` is now actually enforced. It was defined and
  never read, while the row and column caps bound each dimension
  separately — together they still admitted 500 × 64 = 32,000 cells
  against a declared 20,000. A declared limit nobody enforces is worse
  than no constant at all.
- `vendor_pyodide.py` rejects lockfile filenames that are not plain
  basenames. They arrive unverified from the CDN and reach both a URL
  and a write path; the deploy path already failed closed, but
  `--write-hashes` has no such backstop by construction.

### Fixed — `.eml` correctness (CRITICAL)
- **A 50-recipient BCC list collapsed to one recipient.** Addresses were
  joined with `"; "`, and under `policy.SMTP` a semicolon terminates an
  RFC 5322 group — so 49 people silently did not receive the newsletter.
  Found by a 50-recipient test, not by inspection.
- **Long `Content-ID` headers were RFC 2047 encoded-word encoded**,
  breaking the CID reference so the photo did not display. A `Content-ID`
  carries `msg-id` syntax: folding it is legal, but an encoded-word
  inside the identifier is not, and destroys the match against the
  `cid:` reference in the HTML. The production logo filename was long
  enough to trigger it. Fixed by mapping the header to `MessageIDHeader`.

### Changed — honesty about what each backend can do
- `ClipboardMailtoBackend` never reads `draft.bcc`, so BCC simply does
  not arrive on that path. (RFC 6068 does permit a `Bcc` field in a
  `mailto:` URI — RFC 2368 was the version that prohibited it — but it is
  not a *reliable* carrier for ~50 addresses: Windows caps the URI around
  2 KB, handlers differ in what they honour, and RFC 6068 itself warns
  the addresses may leak to other recipients.) The CLI nonetheless
  printed "BCC pre-filled with N recipient(s)" regardless of backend —
  the default path for every macOS, Linux, Thunderbird and webmail
  editor. The recovery an editor reaches
  for on finding BCC empty is the dangerous one: pasting the list into
  To:/Cc:, disclosing ~50 institutional addresses to every recipient and
  every forward. Backends now declare `supports_bcc`, and the message
  names the field and points at `--backend=eml`.

### Added — photo sizing and a message-size budget
- `--max-image-px` / `--image-quality` (defaults 1200 px / 82).
  Measured on a real issue: photos arrived at 1400–1500 px to be
  displayed at 560 px; downscaling took 1.6 MB to 468 KB. EXIF and GPS
  are stripped; orientation is applied first.
- The validator now accounts for attachment overhead (`× 1.37` for
  base64) and warns at 15 MB / hard-fails at 30 MB, against the
  university mail server rather than against Gmail's clip threshold.

## [v1.1.2] — production field trial (2026-04-30)

Two bugs found the first time the toolkit ran on someone else's machine,
plus the feature that trial asked for.

### Fixed
- **Empty mail when the DOCX had no numbered headings.** The strict parse
  found no sections and produced a draft with nothing in it. Added
  `_parse_lenient` as a fallback, and a hard failure for the genuinely
  empty case — the editor now sees the problem in the launcher console
  instead of a blank Outlook draft.
- **macOS read-only failure.** Running the launcher from a folder
  extracted into `~/Downloads` hit the macOS sandbox and the toolkit
  could not write its output. Added `is_writable_location()` and a
  fallback to `~/Documents/Meridian-Newsletter/`.

### Added
- `--output-dir` on `build`, `compose`, `preview` and `all`, so editors
  can choose where the HTML lands.

## [v1.1.1] — audit rounds 15–16 (2026-04-30)

### Fixed
- Chosen-backend convergence and the photo-hosting implications an
  editor was not being told about (round 15).
- Public-name consistency, a filesystem-path leak in an error message,
  and Japanese-nativeness corrections (round 16).
- POSIX positive-control path in the CID drive-letter test.

## [v1.1.0] — CID inline images (2026-04-30)

The release that removed the GitHub account from the editor's setup.

### Added
- **CID inline-image attachments.** Photos are embedded as MIME parts
  rather than hosted, so there is no public URL and no GitHub account to
  create. Phase 1 shipped opt-in via `--image-mode`; Phase 2 made CID the
  default for Outlook and dropped GitHub from the editor-facing setup
  entirely. Hosted `raw.githubusercontent.com` remains for the Apple
  Mail / Gmail-web / Thunderbird path.
- Community-health and discoverability files: `LICENSE` (MIT with an NU
  trademark carve-out), `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, GitHub
  Actions CI across all three platforms, and issue templates.
- A one-click ZIP download link in Setup Step 1.

### Fixed
- Round-12 audit: path traversal in the CID attachment path, plus eight
  others; round-12 re-audit for Phase 1 closeout.

### Changed
- Launcher docs reframe the SmartScreen / Gatekeeper warnings as expected
  rather than as something to worry about.
- Native-Japanese rewrite of the JA README following a six-reviewer round.

### Added
- **`.eml` draft export** (`--backend=eml`, `scripts/mail/eml.py`). Writes
  an RFC 5322 draft next to the rendered HTML; opening it in Outlook
  desktop gives an editable, ready-to-send draft with subject, BCC and
  CID photos in place — no COM, no clipboard, no paste. Explicit-only:
  `matches()` returns False, because **Apple Mail opens `.eml`
  read-only** and making it a macOS default would be a regression
  dressed as a fix.
- **A no-install browser build** (`web/`). A static page that turns a
  filled `issue-N.docx` into that same `.eml`, running the real
  `scripts/` package inside Pyodide. No server, no upload. Pinned to
  Pyodide 0.29.x — `css_inline` has no build for 314.x's ABI.
- `scripts/webapp.py` — the pipeline as one pure function, reusable from
  a server or notebook.
- A CLI/web parity test asserting both pipelines emit byte-identical
  HTML, and a guard that `scripts.webapp` imports with the OS-specific
  modules blocked.

### Fixed (CRITICAL)
- **A crafted DOCX could ship an arbitrary-extension attachment to every
  recipient.** `extract_embedded` gated on magic bytes only and kept the
  attacker's extension, so `word/media/report.hta` beginning with the
  JPEG signature was attached as `application/octet-stream` from the
  editor's own mailbox, under the newsletter's reputation. Now gated on
  extension as well. Pre-existing on the Outlook path; `.eml` and the
  browser page widened the exposure.
- **Fifty recipients could silently become one.** Recipients are joined
  with `"; "` for Outlook COM, but RFC 5322 reads a semicolon as a group
  terminator — `email.policy.SMTP` kept only the first address. A stray
  quote from a CSV paste did the same thing, because `_EMAIL_RE` did not
  exclude `"`.
- **CID photos rendered broken for long filenames.** `Content-ID` is not
  a registered structured header, so a value past the fold width was
  RFC 2047 encoded and no longer matched the `cid:` reference. The
  production masthead logo is exactly long enough to trigger it.

### Fixed (HIGH)
- Decompression bomb: a 400 KB DOCX expanded to 400 MB. Capped on bytes
  actually written, not on the zip's self-reported sizes.
- Brand assets were not embedded on the `--output-dir` path (including
  the macOS read-only fallback), silently producing a partly-external
  email.
- Photos too large to embed were linked from the web with no warning, in
  a mode where nothing publishes them.
- The browser's BCC box bypassed every `recipients.txt` guard.
- The `.eml` body was not 7-bit clean (`cte_type` left at `8bit`).
- The `.eml` carrying ~50 cleartext addresses was created world-readable.
- Nine editor-facing frontend faults, including a rejected file leaving
  the previous one armed, and a corrupt DOCX reported as a toolkit bug.

### Security
- A CSP whose `connect-src` is an allowlist, narrowing where any script
  on the page could send data. Stated precisely, because the distinction
  matters: the application has **no upload endpoint** and all processing
  is local, and the CSP is defence-in-depth on top of that — not proof
  that no exfiltration path exists. The allowlist still contains three
  third-party hosts, and SRI covers only the Pyodide loader, not the four
  files it then fetches. Vendoring the runtime is what would make the
  guarantee absolute.
- `python-docx` version-pinned — it is the one dependency absent from
  Pyodide's lockfile and was resolving unpinned against PyPI at every
  cold load.

## [v1.0.1] — bundle 29 (2026-04-28)

Round-10 closeout. Two regressions from bundle 28 fixed, plus the convergent
cluster across all 7 specialist reviewers. **+20 new regression tests
(201 total).**

### Fixed (HIGH)
- **Highlights cards no longer overflow in Outlook desktop.** Bundle 28's
  `width: 264px` was treated as content-box (264 + 14 + 14 padding = 292 px
  rendered, overflowing the 544 px usable section width by 56 px). Card
  content-width is now `236 px` so the rendered outer hits the 264 px budget.
- **Masthead alignment unified.** Bundle 28 anchored the seal to `middle` and
  the text column to `top`, leaving empty space *both above and below* the
  seal. Both cells are now `vertical-align: middle`.
- **Plaintext heading-marker URL leak fixed.** `<h2><a href="x">Link</a></h2>`
  produced `=== LINK (HTTPS://X.COM) ===`. Headings are now rewritten before
  link expansion.
- **Fullwidth `@` (U+FF20) recipient-validation bypass closed.** A crafted
  `victim＠evil.com` would have passed `_EMAIL_RE`. NFKC now runs before the
  regex so all fullwidth ASCII variants get folded first.
- **README Step 3 ZIP warning reframed** as a forward-looking note keyed to
  "next time you visit github.com" rather than abstract pre-emptive guidance.

### Improved (MEDIUM)
- Plaintext output is CRLF-terminated (RFC 5322).
- `_BLOCK_TAGS` no longer includes `thead` / `tbody` / `tfoot` (~30%
  whitespace recovery).
- Strict-fallback plaintext preserves block boundaries instead of single-line
  collapse (no more SpamAssassin `LONG_LINE` trip).
- URL allowlist case-insensitive (legitimate `HTTPS://...` survives).
- `pywintypes.com_error` caught explicitly (older pywin32 < 228 doesn't
  derive from `OSError`).
- `ComposeOutcome.__str__` no longer emits `DeprecationWarning` (lazy-`%s`
  log calls were triggering it on every INFO line).
- `_KEEP_CHARS_WITH_ZWJ` precomputed at module load.
- `scripts/html_utils.py` expanded with `parse_html()` + `visible_text()`,
  eliminating 4× BeautifulSoup duplication.
- Subhead 12 → 13 px (was reading as inline emphasis below 14 px body).
- Highlights gutter `&#8203;` + `mso-line-height-rule:exactly` (matched
  divider).
- Masthead padding 16/18 conflict resolved.
- Heading uppercase consistent across simple-string and nested-tag paths.
- README EN ↔ JA Q&A parity restored ("Dean photo / logo not visible"
  added to JA).

### Polish (LOW)
- `_subject_for` → `_subject_from_path`; `_legacy_str` → `_format_legacy`.
- Publisher `TypeError` message caps `repr` at 80 chars.
- Validator drops hidden elements before scanning anchor URLs.
- Subject preview-truncation tip points editors at the actual source
  (`MONTH YEAR` in masthead).
- Validation-fail message names the `ERROR:` marker.
- Print-mode Q&A wording rephrased.

## [v1.0.0] — bundle 28 (2026-04-28)

Round-9 closeout. First production-tagged release.

### Added
- `scripts/html_utils.py` — shared `remove_hidden_elements(soup)`.
- `scripts/mail/plaintext.py` — multipart/alternative plaintext converter
  with heading markers, bullet glyphs, URL allowlist.
- `ComposeOutcome` typed dataclass (replaces stringly-typed `compose()`
  return).
- Subject-length thresholds: 50 (preview) + 78 (spam-heuristic).
- Publisher rejects `issue <= 0` AND non-int issue numbers.
- Bundle-26 / bundle-27 fixes (validate-before-write, masthead hairline
  frame, ZWJ default-strip, build_template package split, ZIP self-check
  hardening, JP/EN README parity, print stylesheet).

## Earlier history

The toolkit was built end-to-end across **bundles 1–27**, with each fix
bundle following a specialist-review round (architect / Python / security /
code / visual / UX / email-deliverability). See `git log --all --oneline`
for the full archaeology.

---

[v1.5.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.5.0
[v1.4.2]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.4.2
[v1.4.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.4.1
[v1.4.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.4.0
[v1.3.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.3.0
[v1.2.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.2.0
[v1.1.2]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.2
[v1.1.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.1
[v1.1.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.0
[v1.0.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.1-bundle29
[v1.0.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.0-bundle28

---

## Tagging note

`v1.2.0` and `v1.3.0` were written up before they were tagged: with tag
signing on, `git tag -a` waited for an SSH-key passphrase that a
non-interactive run cannot supply. Both were tagged afterwards at the
commits their entries describe -- `v1.2.0` at `b361a16` (SSH-signed),
`v1.3.0` at `f67b228` (unsigned, like the v1.1.x tags) -- and published
as GitHub Releases on 2026-09-14.
