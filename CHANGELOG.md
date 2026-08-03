# Changelog

All notable changes to MERIDIAN are documented here.

The toolkit follows [Semantic Versioning](https://semver.org). The detailed
per-bundle commit history (29 fix bundles across 10 specialist-review rounds)
is preserved in `git log` for archaeology.

## [v1.3.0] — see it the way recipients will (2026-08-03)

Four HIGH fixes, three new preview capabilities, offline support and a
restyled builder page. Two of the fixes came from field reports — "when
downloading the html the images are gone" and "[date] is not highlighted
in the preview"; the rest were found while investigating those, and the
restyle was requested separately. **468 tests passing** on Linux, macOS
and Windows.

> **Note on v1.2.0.** It was written up but never tagged, so nothing was
> ever released under that name. Both sections are real and separate;
> see the tagging note at the foot of this file.

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

[v1.3.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/commit/f67b228
[v1.2.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/commit/b361a16
[v1.1.2]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.2
[v1.1.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.1
[v1.1.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.0
[v1.0.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.1-bundle29
[v1.0.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.0-bundle28

---

## Tagging note

`v1.2.0` and `v1.3.0` are both documented above but were not tagged at
the time they were written: `tag.gpgSign = true` with an SSH key whose
passphrase cannot be supplied non-interactively, so `git tag -a` waits
for input that never comes. The v1.1.x tags predate that setting and are
unsigned.

Both are still tag-able at the right commits:

    git tag -a v1.2.0 b361a16 -m "v1.2.0 -- .eml export, browser build"
    git tag -a v1.3.0 f67b228 -m "v1.3.0 -- see it the way recipients will"
    git push origin v1.2.0 v1.3.0

Both commits are pinned deliberately. `HEAD` would have been wrong by the
time anyone ran this -- the commit adding these very lines lands after
it. `f67b228` is the last code change in v1.3.0; this entry documents it
from immediately afterwards.

Add `--no-sign` to match the unsigned v1.1.x tags.
