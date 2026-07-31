# Changelog

All notable changes to MERIDIAN are documented here.

The toolkit follows [Semantic Versioning](https://semver.org). The detailed
per-bundle commit history (29 fix bundles across 10 specialist-review rounds)
is preserved in `git log` for archaeology.

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

[v1.2.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.2.0
[v1.1.2]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.2
[v1.1.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.1
[v1.1.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.1.0
[v1.0.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.1-bundle29
[v1.0.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.0-bundle28
