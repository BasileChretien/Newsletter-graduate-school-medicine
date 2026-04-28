# MERIDIAN — The Newsletter Toolkit

> **MERIDIAN** — *Where medicine meets the world.*

Welcome! This is the toolkit for producing the **Graduate School of Medicine, Nagoya University** newsletter. It does two things for you:

1. Gives you a **beautiful Word template** (`Meridian_Newsletter_Template.docx`) — already styled with the school's colors, fonts, logo, and Dean photo.
2. Turns your filled-in Word file into a **polished email** (an HTML file) you can paste straight into Gmail or Outlook.

You do **not** need to be a programmer to use this. Follow the steps below.

---

## What you need (one-time setup)

You'll set this up once on your computer. After that, every issue takes only a few minutes.

### 1. Install Python

Python is the small program that runs the toolkit.

- **Windows:** download from <https://www.python.org/downloads/> and run the installer. **Important:** on the first screen, tick the box that says **"Add Python to PATH"**. Then click *Install Now*.
- **macOS:** Python is usually already installed. Open the **Terminal** app and type `python3 --version` then press Enter. If it shows a number like `3.12.x`, you're done.

### 2. Open a command window in the project folder

A "command window" is a black/white box where you type instructions. Don't worry — you'll only ever type a couple of lines.

- **Windows:** open File Explorer, find the folder `Newsletter-graduate-school-medicine`, click the address bar at the top, type `cmd`, and press Enter. A black window opens.
- **macOS:** open **Terminal**, type `cd ` (with a space), then drag the folder onto the Terminal window, and press Enter.

### 3. Install the toolkit

Copy and paste this single line into the command window and press Enter:

```
pip install -r requirements.txt
```

You'll see lots of text scroll by. When it finishes, you're ready. **You will never have to do this again on this computer.**

---

## How to make a newsletter (every issue)

Here's the full routine. It takes about 10 minutes once you're used to it.

### Step 1 — Open the template in Word

Double-click **`Meridian_Newsletter_Template.docx`**. Word opens it. Save a copy with a clear name like:

```
issue-3.docx
```

(or whichever issue number you're working on).

### Step 2 — Fill in your content

In the file you just saved:

- Replace the masthead's **issue line** ("VOL. XX | ISSUE NO. XX | MONTH YEAR") with the real volume, issue number, and month.
- Replace **`[Dean's Name]`**, **`[Author(s)]`**, **`[Visitor Name]`**, **`[YYYY/MM/DD]`** etc. with your real text.
- Replace the message paragraphs (the gray "Lorem ipsum"-style text) with the actual newsletter content.
- **Do not rename the section titles** (1. Message from the Dean, 2. Featured Highlights, etc.) — the toolkit relies on them.

Save the file when you're done.

### Step 3 — Add photos (optional)

If you want photos in the newsletter (a partner-lab snapshot, a signing-ceremony picture, an event photo, etc.):

1. Open the folder **`drop-images/`** inside the project folder.
2. Copy your photos in there.
3. **Rename each photo** following this pattern:

```
s<section>_<order>_<short-name>.jpg
```

| Part | What it means |
|---|---|
| `s1` to `s7` | the section number where the photo belongs (see table below) |
| `01`, `02`, ... | the order if you have several in the same section |
| `short-name` | a short hyphenated label (lowercase letters, digits, hyphens) |

Section numbers:

| Number | Section |
|---|---|
| 1 | Message from the Dean |
| 2 | Featured Highlights |
| 3 | Research & Academic Updates |
| 4 | International Collaboration |
| 5 | Education & Student Activities |
| 6 | Events & Announcements |
| 7 | Contact Information |

**Examples:**

- `s2_01_award-ceremony.jpg` — first photo of section 2 (Featured Highlights), an award ceremony
- `s4_01_mou-signing.jpg` — first photo of section 4 (International), an MOU signing
- `s4_02_partner-lab.png` — second photo of section 4

Allowed file types: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`. **No spaces** in filenames.

> **You don't need to add the Dean photo or the school logo** — those two are already built in.

### Step 4 — Run the toolkit

Back in the command window, type:

```
python build_newsletter.py all --input issue-3.docx --issue 3
```

(Replace `3` with the issue number you're working on, in both spots.)

This does everything in one go:

- Reads your Word file
- Pulls in any photos from `drop-images/`
- Uploads the photos so they're publicly visible
- Builds the email and opens it in your web browser

When the browser opens, you'll see exactly what the email will look like.

### Step 5 — Send the email

You have two options:

**Option A — Paste into Gmail or Outlook (easiest):**

1. In your web browser (showing the preview), select all the page (`Ctrl+A` on Windows, `⌘+A` on macOS).
2. Copy it (`Ctrl+C` / `⌘+C`).
3. Open Gmail or Outlook, click **Compose**, and paste into the message body (`Ctrl+V` / `⌘+V`).
4. Add the recipients and a subject line, then send.

**Option B — Send the HTML file:**

The file `dist/issue-3.html` is a self-contained email. You can also forward it as an attachment, or upload it to a mailing platform that accepts HTML.

That's it!

---

## Common questions

**❓ I don't see the Dean photo or the logo in the preview.**
Make sure you ran the full command (`python build_newsletter.py all ...`) and not just `build` — the `all` command also publishes the photos to the web. If they still don't show, try refreshing your browser.

**❓ The preview shows a broken-image icon for one of my drop-folder photos.**
Most likely the filename doesn't match the expected pattern. Check that it starts with `s` then a digit between 1 and 7, then `_`, etc. Examples: `s3_01_lab.jpg`, **not** `S3-01-lab.jpg` or `lab photo.jpg`.

**❓ I need to redo issue 3 — what do I do?**
Just re-run `python build_newsletter.py all --input issue-3.docx --issue 3`. It will overwrite the previous output. No harm done.

**❓ I want to change the colors / fonts / title of the template.**
Those are intentionally fixed so every issue stays consistent. Ask the developer (or the person who set this up for you) to update the design.

**❓ I want to add a new section.**
Section names and the order are part of the design. If you really need a new section, ask the developer — it requires a small code change too.

**❓ Where is the email file saved?**
In the `dist/` folder. For issue 3, it's `dist/issue-3.html`. You can open it any time by double-clicking it.

**❓ Where do my drop-folder photos end up?**
In `assets/issue-3/` (for issue 3). They're also pushed to GitHub so they have a public web address.

**❓ I'm getting an error message I don't understand.**
Copy the full red text and send it to the developer. Most errors are clear about what went wrong (e.g. "image filename doesn't match the convention").

---

## Quick reference card

| What you want to do | Type this |
|---|---|
| Make a newsletter for issue N (full routine) | `python build_newsletter.py all --input issue-N.docx --issue N` |
| Just rebuild the email without uploading | `python build_newsletter.py build --input issue-N.docx --issue N --no-remote-check` |
| Open the latest preview in your browser | `python build_newsletter.py preview --issue N` |
| Re-upload only the photos | `python build_newsletter.py publish-images --issue N` |

(Replace `N` with the issue number every time.)

---

## What's in this folder?

You can ignore most of these — they just need to be there.

| Folder / file | What it's for |
|---|---|
| `Meridian_Newsletter_Template.docx` | **The template you fill in.** Open in Word. |
| `drop-images/` | **Drop photos here** (with the right filename). |
| `dist/` | The finished email files end up here. |
| `assets/` | Where uploaded photos are kept. |
| `images/` | Permanent images (school logo, Dean photo). |
| `NagoyaU_MedSchool_Newsletter_Template-2.docx` | Original template, kept as reference. |
| `build_newsletter.py`, `scripts/`, `templates/`, `tests/` | The toolkit's machinery. **Don't touch.** |

---

## For developers

Technical details for whoever maintains the toolkit:

- **Stack:** Python 3.12, `python-docx`, `Jinja2`, `css_inline`, `click`, `pytest`.
- **Visual identity:** primary `#8B1A1F` (NU wine red), accent `#C9A96E` (warm gold), text `#1C1C1E`, muted `#6B6B70`, cream `#F7F2EA`. Cambria headings, Calibri body.
- **Email-client compatibility:** 600px table-based layout, inline CSS via `css_inline`, MSO conditional ghost tables for Outlook desktop, `meta color-scheme` for dark-mode best effort. Validator emits warning if rendered HTML exceeds Gmail's 102 KB clip threshold.
- **Module map:** `scripts/build_template.py` (DOCX builder) · `scripts/docx_parser.py` (DOCX → `Newsletter` dataclass) · `scripts/image_handler.py` (embedded + drop-folder, GitHub raw URL builder) · `scripts/renderer.py` + `templates/*.j2` (Jinja2 → HTML) · `scripts/inliner.py` (`css_inline`) · `scripts/validator.py` (HEAD checks + size warning) · `scripts/publisher.py` (git add/commit/push of `assets/issue-N/`) · `scripts/oxml_helpers.py` (raw OXML for shading, borders, fields).
- **Constraints:** section names and content are not edited by the script — only the visual style is. Nested tables in DOCX are unsupported. Drop-image regex: `^s(?P<section>\d+)_(?P<order>\d+)_(?P<slug>[a-z0-9-]+)\.(jpg|jpeg|png|webp|gif)$`.
- **Tests:** `python -m pytest tests/ --cov=scripts` — currently 34 tests, core modules 76–100% covered.
- **Rebuild the template after design tweaks:** `python build_newsletter.py build-template`.
- **Smoke test:** `python build_newsletter.py build --input Meridian_Newsletter_Template.docx --issue 0 --no-remote-check`.
