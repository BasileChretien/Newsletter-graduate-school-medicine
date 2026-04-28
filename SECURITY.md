# Security policy

## Reporting a vulnerability

If you find a security issue in MERIDIAN, please **do not** open a public
GitHub issue. Email the maintainer at the address listed in the repo's
"About" page, or open a private security advisory via GitHub's
[Security → Advisories → Report a vulnerability](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/security/advisories/new)
flow.

I'll respond within 7 days.

## Scope

The toolkit reads a Word `.docx` from the editor's local disk, generates
HTML, opens an Outlook draft, and pushes images to a public GitHub
repository. Realistic attack surfaces:

- **Crafted DOCX** — a malicious newsletter file could try to:
  - Smuggle a recipient address that bypasses validation (e.g. via
    Unicode normalization, invisible joiner characters, or fullwidth
    ASCII variants). The toolkit's `scripts/text_utils.strip_invisibles`
    + `normalize_compatibility` pipeline runs against the recipients
    list and the email subject; a separate masthead-token guard runs
    against the rendered HTML. See round-9 / round-10 review logs for
    the specific vectors covered.
  - Inject an HTML hyperlink with an unsafe scheme (`javascript:`,
    `data:`, `file:`, `tel:`, `vbscript:`). The plaintext converter
    enforces an `http://` / `https://` / `mailto:` allowlist
    case-insensitively; the visible label survives but the URL is
    dropped.
  - Hide a malicious anchor inside a `display:none` / `visibility:hidden`
    / `[hidden]` element. The validator now strips hidden elements
    before scanning anchor URLs (round-10 fix).
  - Embed an image whose magic bytes don't match a supported raster
    format. `scripts/image_handler.py` rejects anything that's not
    detectably JPEG/PNG/WebP before publishing.
- **Crafted `recipients.txt`** — a header-injection attempt
  (`victim@x.com\nbcc:attacker@y.com`) would split into multiple BCC
  entries on the wire. The reader strips CR/LF and rejects any line
  that contains a separator char (`;` `,` `<` `>`).
- **Public asset push** — `scripts/publisher.publish_assets` rejects
  `issue <= 0` and any non-int issue number (no float / string / bool
  coercion paths) so the local development sandbox `assets/issue-0/`
  can't be accidentally pushed to the public repo. `assets/issue-0/`
  is also `.gitignore`d as belt-and-braces.

## What's NOT in scope

- The editor's outgoing mail server. MERIDIAN opens an Outlook *draft*;
  the actual SMTP send + DKIM signing happens after the editor reviews
  and clicks Send. Mail-server reputation belongs to your IT team.
- The editor's GitHub credentials. `gh auth` / GitHub Desktop manages
  those; the toolkit uses whatever's already authenticated.
- The web hosting of published photos. They're served via
  `raw.githubusercontent.com`, which is a CDN under GitHub's control,
  not the toolkit's. If a recipient's corporate filter quarantines the
  domain, the README documents a GitHub Pages mirror workaround.

## Past security work

The toolkit went through 4 dedicated security-review rounds (rounds 7,
8, 9, 10) plus continuous coverage in every other round. Specific
findings closed:

| Round | Vector | Mitigation |
|---|---|---|
| 8 | NBSP bypassed unfilled-masthead guard | NFKC + whitespace collapse before the regex |
| 9 | ZWJ kept in `_KEEP_CHARS` allowed `victim<ZWJ>@evil.com` past `_EMAIL_RE` | ZWJ stripped by default; rendering callers opt in via `keep_zwj=True` |
| 10 | Fullwidth `@` (U+FF20) bypassed `_EMAIL_RE` | NFKC normalization runs before regex matching in `load_recipients` |
| 10 | Hidden `<a href>` survived audit-trail collection | `remove_hidden_elements` runs before anchor scanning |
| 10 | `publisher.publish_assets(0.5)` reached the filesystem layer | Explicit `isinstance(issue, int)` + bool exclusion |
| 10 | Case-sensitive scheme allowlist could let mixed-case `Javascript:` slip past if BS4 changed normalization | `_is_safe_scheme` lowercases before matching |

See `CHANGELOG.md` for the full bundle history and `git log` for
per-commit detail.
