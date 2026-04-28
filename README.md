# MERIDIAN — Nagoya University Graduate School of Medicine Newsletter

Pipeline that turns a filled Word newsletter into a polished HTML email.

> **MERIDIAN** — *Where medicine meets the world.*

This repository contains:

1. **`Meridian_Newsletter_Template.docx`** — the modernized newsletter template (wine red + warm gold, Cambria masthead, zebra-striped tables).
2. **A Python pipeline** that takes a filled DOCX and produces a polished, email-client-compatible HTML file ready to paste into Gmail/Outlook compose.

The original template (`NagoyaU_MedSchool_Newsletter_Template-2.docx`) is preserved as a reference and is not modified.

---

## Quick start (for editors)

```bash
# 1. Set up Python (one-time)
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt

# 2. Open Meridian_Newsletter_Template.docx in Word, fill it in,
#    and save as e.g. issue-3.docx

# 3. Drop any photos into drop-images/ using the naming convention:
#    s<section#>_<order>_<slug>.jpg
#    e.g. s1_01_dean.jpg     (Dean photo, section 1)
#         s4_01_partner.jpg  (Partner snapshot, section 4)

# 4. Run the full pipeline
python build_newsletter.py all --input issue-3.docx --issue 3
```

The script will:
- extract embedded images and ingest your `drop-images/` files into `assets/issue-3/`
- render `dist/issue-3.html`
- commit + push the assets so GitHub raw URLs are live
- open the HTML preview in your browser

Then **paste** the HTML into a Gmail compose window or Outlook "Send as email" and it will render correctly.

---

## Image workflow

Two ways to add images:

| Method | When to use | Where |
|---|---|---|
| **Embed in DOCX** | Dean photo, anything you want visually placed in Word | inside the document |
| **Drop folder** | Most images — clearest control over placement | `/drop-images/` |

### Drop-folder naming convention

Filename pattern: `s<section>_<order>_<slug>.<ext>`

| Section | What it covers |
|---|---|
| 1 | Message from the Dean |
| 2 | Featured Highlights |
| 3 | Research & Academic Updates |
| 4 | International Collaboration |
| 5 | Education & Student Activities |
| 6 | Events & Announcements |
| 7 | Contact Information |

Examples:
- `s1_01_dean.jpg` — Dean photo, first image of section 1
- `s4_01_signing-ceremony.jpg` — first image of section 4
- `s4_02_partner-lab.png` — second image of section 4

Allowed extensions: `jpg`, `jpeg`, `png`, `webp`, `gif`. Slug is lowercase letters / digits / hyphens.

The script copies validated images into `assets/issue-<N>/` and refers to them via public GitHub raw URLs.

---

## CLI commands

```bash
# Generate the modern template (run once after a design tweak)
python build_newsletter.py build-template

# Build only — produces dist/issue-N.html (no git push)
python build_newsletter.py build --input filled.docx --issue 5 --no-remote-check

# Push assets to GitHub so raw URLs go live
python build_newsletter.py publish-images --issue 5

# Open the rendered HTML in a browser
python build_newsletter.py preview --issue 5

# All-in-one: build → publish → open preview
python build_newsletter.py all --input filled.docx --issue 5
```

---

## Repo layout

```
.
├── Meridian_Newsletter_Template.docx     # styled template (fill this)
├── NagoyaU_MedSchool_Newsletter_Template-2.docx  # original (reference)
├── build_newsletter.py                   # CLI entrypoint
├── scripts/
│   ├── build_template.py                 # rebuilds the styled template
│   ├── config.py                         # palette, paths, repo coords
│   ├── docx_parser.py                    # DOCX → structured Newsletter
│   ├── image_handler.py                  # embedded + drop-folder ingest
│   ├── inliner.py                        # CSS inlining (css_inline)
│   ├── oxml_helpers.py                   # raw OXML utilities
│   ├── publisher.py                      # git add/commit/push assets
│   ├── renderer.py                       # Jinja2 → HTML
│   └── validator.py                      # link/image/size checks
├── templates/
│   ├── newsletter.html.j2                # 600px table-based skeleton
│   ├── partials/_block.html.j2
│   └── styles.css                        # source CSS (inlined later)
├── images/
│   └── Nagoya_University_Graduate_school_medicine_logo.jpg  # permanent brand logo
├── assets/
│   └── issue-<N>/                        # per-issue published images
├── drop-images/                          # editor drop zone (gitignored)
├── dist/issue-<N>.html                   # final output (gitignored)
└── tests/
```

---

## Visual identity

| Role | Hex |
|---|---|
| Primary (masthead band, section bars, table headers) | `#8B1A1F` (NU wine red) |
| Accent (dividers, bullet markers, issue line pipes) | `#C9A96E` (warm gold) |
| Body text | `#1C1C1E` |
| Muted (captions, footer) | `#6B6B70` |
| Cream tint (zebra rows, masthead backdrop) | `#F7F2EA` |

Headings: **Cambria**. Body: **Calibri**. Both ship with Office on Windows and macOS — no external font load is required for either Word or email rendering.

---

## Email-client compatibility

- **Gmail web / iOS / Android** — supported. Watch for the 102KB clip threshold; the validator warns if the HTML grows past it.
- **Outlook 2016+ desktop** — supported via 600px ghost table and MSO conditional comments.
- **Outlook.com / Apple Mail / iOS Mail** — supported.
- **Dark mode** — best-effort via `meta name="color-scheme"`. Some clients (Gmail iOS) force inversion regardless.

Validator output (`Size`, `Images`, `Links`) is printed after each `build`. A non-zero exit code indicates broken image URLs or other hard errors.

---

## Constraints

- Section names and section content cannot change. The template builder restyles only — it does not edit text. Add or rename sections only with editorial sign-off, then update `SUBHEAD_TEXTS` in `scripts/build_template.py` and `scripts/docx_parser.py`.
- Nested tables in the DOCX are not supported by the parser.
- `publish-images` requires the local clone to be a working git checkout with push access.

---

## Development

```bash
# Run tests
python -m pytest tests/ --cov=scripts

# Rebuild the template after a design change
python build_newsletter.py build-template

# Quick end-to-end smoke test
python build_newsletter.py build --input Meridian_Newsletter_Template.docx --issue 0 --no-remote-check
```
