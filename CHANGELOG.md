# Changelog

All notable changes to MERIDIAN are documented here.

The toolkit follows [Semantic Versioning](https://semver.org). The detailed
per-bundle commit history (29 fix bundles across 10 specialist-review rounds)
is preserved in `git log` for archaeology.

## [Unreleased] — `.eml` export + browser build

> **Note:** this file skips v1.1.0–v1.1.2. Those shipped from `git log`
> without CHANGELOG entries; the gap is real and predates this branch.

Two capabilities, plus the fixes that fell out of four specialist reviews
(security, Python, architecture, frontend) and three CodeRabbit passes.
**+88 regression tests (378 passed, 2 skipped).**

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

[v1.0.1]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.1-bundle29
[v1.0.0]: https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/tag/v1.0.0-bundle28
