# MERIDIAN — The Newsletter Toolkit

> **MERIDIAN** — *Where medicine meets the world.*

Welcome! This is the toolkit for producing the **Graduate School of Medicine, Nagoya University** newsletter. It does two things for you:

1. Gives you a **beautiful Word template** (`Meridian_Newsletter_Template.docx`) — already styled with the school's colors, fonts, logo, and Dean photo.
2. Turns your filled-in Word file into a **polished email** that opens **directly in your usual email app** (Outlook, Apple Mail, Thunderbird, Gmail in your browser, …) with the newsletter already in the body. You only have to type the recipients and click Send.

You do **not** need to be a programmer to use this. Follow the steps below.

---

## What you need (one-time setup)

You'll set this up once on your computer. After that, every issue takes only a few minutes.

### 1. Download the toolkit onto your computer

You need to copy this project's folder onto your machine. The simplest way:

1. Open this URL in a web browser: <https://github.com/BasileChretien/Newsletter-graduate-school-medicine>
2. Click the green **Code** button near the top right of the page.
3. In the menu that drops down, click **Download ZIP**.
4. Save the ZIP file (it goes to your Downloads folder by default).
5. Open the ZIP file and **extract / unzip** it to somewhere easy to find — your **Documents** folder works well. After extracting you'll have a folder called `Newsletter-graduate-school-medicine-main` (or similar). **Rename it to `Newsletter-graduate-school-medicine`** if you want, or leave it as-is.

> **Where should I put the folder?** Anywhere you can find again. `Documents\Newsletter-graduate-school-medicine` is a good default. You'll point the command window to wherever you put it in step 3 below.

> **Power users:** if you're comfortable with Git, you can `git clone https://github.com/BasileChretien/Newsletter-graduate-school-medicine.git` instead — same effect, plus you get future updates by running `git pull`.

### 2. Install Python

Python is the small program that runs the toolkit.

- **Windows:** download from <https://www.python.org/downloads/> and run the installer. **Important:** on the first screen, tick the box that says **"Add Python to PATH"**. Then click *Install Now*.
- **macOS:** Python is usually already installed. Open the **Terminal** app and type `python3 --version` then press Enter. If it shows a number like `3.12.x`, you're done.

### 3. Open a command window inside the project folder

A "command window" is a black/white box where you type instructions. Don't worry — you'll only ever type a couple of lines.

You need it to be **opened inside** the folder you downloaded in step 1 (so it knows which project to work on).

- **Windows:**
  1. Open **File Explorer** (the folder icon on your taskbar).
  2. Navigate to the folder where you saved the project — for example `Documents\Newsletter-graduate-school-medicine`. Double-click into it so you're seeing files like `Meridian_Newsletter_Template.docx` and `README.md` listed.
  3. Click once in the **address bar at the top** of the window (the bar that shows the folder path), so the path becomes editable.
  4. Type `cmd` and press Enter. A black window opens — it's already pointing at the project folder. ✓

- **macOS:**
  1. Open **Terminal** (Applications → Utilities → Terminal).
  2. Type `cd ` (the letters c, d, then a space — don't press Enter yet).
  3. Open Finder, find the project folder, and **drag it onto the Terminal window**. The folder's path is pasted automatically.
  4. Press Enter. The terminal is now pointing at the project folder. ✓

> **Quick check:** type `dir` (Windows) or `ls` (macOS) and press Enter. You should see a list that includes `build_newsletter.py`, `Meridian_Newsletter_Template.docx`, etc. If you see those, you're in the right folder.

### 4. Install the toolkit

Still in the command window, copy and paste this single line and press Enter:

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

**Just paste them straight into the Word file**, exactly where you want them to appear in the email. The toolkit will detect them automatically.

In Word: place your cursor where you want the photo → **Insert → Picture** → choose the file → resize it by dragging the corners. That's it. The photo appears in the email at the same spot, at roughly the same size, with the email's standard styling around it.

**Tips:**

- Resize the photo in Word to roughly the size you want it in the email (don't worry about being precise — the toolkit caps very large images so they fit nicely).
- If the photo looks too big, drag a corner inward in Word.
- You can add as many photos as you want, in any section.

> **The Dean photo and the school logo are already built in.** You don't need to add them yourself.

> Power-user shortcut: there's also a `drop-images/` folder for batch-adding photos via a filename convention (`s<section>_<order>_<slug>.jpg`). Most editors will never need this — pasting into Word is faster.

### Step 4 — Run the toolkit

Back in the command window, type:

```
python build_newsletter.py all --input issue-3.docx --issue 3
```

(Replace `3` with the issue number you're working on, in both spots.)

This does everything in one go:

- Reads your Word file
- **Picks up every photo you pasted in Word** (and any extras in `drop-images/`)
- Uploads the photos so they're publicly visible
- Builds the email
- **Opens a draft email in your default email app** with the newsletter already in the body and the subject line filled in

### Step 5 — Pick recipients and send

What happens depends on which email app your computer is set up to use by default — the toolkit detects this automatically:

- **If your default is Microsoft Outlook (desktop):** Outlook pops up a new draft message. The newsletter is already in the body and the subject line is filled in. **You only have to type the recipients in the To: field and click Send.**

- **If your default is Apple Mail, Thunderbird, Gmail in your browser, or anything else:** the toolkit copies the formatted newsletter to your clipboard and opens a new blank message in your usual email app, with the subject line filled in. Click in the message body, press `Ctrl+V` (or `⌘+V` on macOS) to paste the newsletter, type the recipients, and click Send.

**Not sure which one your computer uses?** Run this to find out:

```
python build_newsletter.py detect-mail
```

That's it!

> **Tip:** if Outlook doesn't open or the wrong app shows up, see "Common questions" below.

---

## Common questions

**❓ I don't see the Dean photo or the logo in the preview.**
Make sure you ran the full command (`python build_newsletter.py all ...`) and not just `build` — the `all` command also publishes the photos to the web. If they still don't show, try refreshing your browser.

**❓ The preview shows a broken-image icon where one of my photos should be.**
Most likely the photos haven't been pushed to the public web yet. Re-run `python build_newsletter.py all ...` (note: `all`, not `build`) — that step uploads them. Refresh the preview. If you used the `drop-images/` folder, also check that the filename matches the pattern `s<section>_<order>_<slug>.jpg` (e.g., `s3_01_lab.jpg`, **not** `S3-01-lab.jpg` or `lab photo.jpg`).

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

**❓ Which email app will the toolkit use?**
Whichever one your computer is configured to use by default for the `mailto:` links you click on websites. Run `python build_newsletter.py detect-mail` to see what the toolkit detected. To change it: open Windows Settings → *Apps* → *Default apps* → *Email*. On macOS: open the Mail app → *Preferences* → *General* → *Default email reader*.

**❓ My default is Outlook but the toolkit opened my browser instead.**
This sometimes happens if Outlook isn't currently running, or if a recent Office update changed the integration. As a workaround, run `python build_newsletter.py all ... --backend default` — that uses the same fallback path as for non-Outlook clients (clipboard + blank draft). Or open Outlook first, then re-run the command.

**❓ The email opened but the newsletter isn't in the body — I just see a blank message.**
You're using the non-Outlook path. The newsletter is on your clipboard — click into the message body and press `Ctrl+V` (or `⌘+V` on macOS).

**❓ I'm getting an error message I don't understand.**
Copy the full red text and send it to the developer. Most errors are clear about what went wrong (e.g. "image filename doesn't match the convention").

---

## Quick reference card

| What you want to do | Type this |
|---|---|
| Make a newsletter for issue N (full routine) | `python build_newsletter.py all --input issue-N.docx --issue N` |
| Just rebuild the email without uploading | `python build_newsletter.py build --input issue-N.docx --issue N --no-remote-check` |
| Open the latest preview in your browser | `python build_newsletter.py preview --issue N` |
| Open the email draft (after a previous build) | `python build_newsletter.py compose --issue N --input issue-N.docx` |
| Re-upload only the photos | `python build_newsletter.py publish-images --issue N` |
| Check which email app the toolkit will use | `python build_newsletter.py detect-mail` |

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
