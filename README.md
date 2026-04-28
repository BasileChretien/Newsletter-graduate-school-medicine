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

## ⬇️ [**CLICK HERE TO DOWNLOAD THE TOOLKIT (ZIP)**](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/archive/refs/heads/main.zip)

[![Download ZIP](https://img.shields.io/badge/⬇%20Download-Toolkit%20(ZIP)-8B1A1F?style=for-the-badge&logo=github)](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/archive/refs/heads/main.zip)

Click the link above, save the ZIP file (it goes to your **Downloads** folder by default), then:

1. Open the ZIP file and **extract / unzip** it to somewhere easy to find — your **Documents** folder works well.
2. After extracting you'll have a folder called `Newsletter-graduate-school-medicine-main` — **rename it to `Newsletter-graduate-school-medicine`** if you want a cleaner name, or just leave it.
3. Remember where you put it — you'll open it in File Explorer / Finder when you make a newsletter.

<details>
<summary><b>Prefer to use the GitHub website by hand?</b></summary>

1. Open <https://github.com/BasileChretien/Newsletter-graduate-school-medicine> in a web browser.
2. Click the green **Code** button near the top right.
3. In the menu that drops down, click **Download ZIP**.
4. Continue from step 1 above (extract, find, rename).
</details>

<details>
<summary><b>Power users — use Git instead?</b></summary>

```
git clone https://github.com/BasileChretien/Newsletter-graduate-school-medicine.git
```

You get future updates with a single `git pull`.
</details>

### 2. Install Python

Python is the small program that runs the toolkit.

- **Windows:** download from <https://www.python.org/downloads/> and run the installer. **Important:** on the first screen, tick the box that says **"Add Python to PATH"**. Then click *Install Now*.
- **macOS:** Python is usually already installed. You'll find out automatically the first time you double-click the launcher in the next section.

That's it for setup. **No command window, no `pip install`, no `cd` — the toolkit handles all of that itself the first time you run it.**

---

## How to make a newsletter (every issue)

Here's the full routine. It takes about 10 minutes once you're used to it.

### Step 1 — Open the template in Word and save with the right name

Double-click **`Meridian_Newsletter_Template.docx`**. Word opens it. Use **File → Save As** and save a **copy** in the **same folder** (next to `Make Newsletter.bat`).

> ⚠️ **The filename matters.** Save it as exactly:
>
> ```
> issue-N.docx
> ```
>
> where `N` is the issue number — for example **`issue-3.docx`** for issue 3, **`issue-12.docx`** for issue 12.

If you stick to that pattern, the launcher (Step 4) will **auto-fill the filename for you** — you just press Enter. You don't have to type it.

| ✅ Good | ❌ Will work but you'll have to type the full name |
|---|---|
| `issue-3.docx` | `Issue 3.docx` *(space, capital I)* |
| `issue-12.docx` | `newsletter-spring-2026.docx` |
| `issue-04.docx` | `Meridian Issue 3.docx` |

Rules: lowercase `issue`, then a hyphen, then digits, then `.docx`. **No spaces.**

> **Don't overwrite the original template.** Always save a copy — keep `Meridian_Newsletter_Template.docx` untouched so you can start fresh next issue.

### Step 2 — Fill in your content

In the file you just saved:

- Replace the masthead's **issue line** ("VOL. XX | ISSUE NO. XX | MONTH YEAR") with the real volume, issue number, and month.
- Replace the bracketed placeholders such as **`[Author(s)]`**, **`[Paper Title]`**, **`[Visitor Name]`**, **`[YYYY/MM/DD]`**, **`[Country]`** etc. with your real text.
- Replace the gray "Lorem ipsum"-style paragraphs with the actual newsletter content.
- **Do not rename the section titles** (1. Message from the Dean, 2. Featured Highlights, etc.) — the toolkit relies on them.

> **The dean's name and photo are already filled in for you** (currently *Prof. Masahisa Katsuno*) — you don't need to touch the credentials block or the signature line. If the dean changes, ask the developer to update the template.

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

### Step 4 — Double-click the launcher

In the project folder, find this file and **double-click it**:

- **Windows:** `Make Newsletter.bat`
- **macOS:** `Make Newsletter.command`

A small black window opens and asks you two things:

```
Issue number (e.g. 3): 3
Word file [issue-3.docx]:        ← just press Enter to accept the suggestion
```

That's it — type `3` (or whatever issue you're on), press Enter twice, and let it run. On the very first time you do this, the toolkit installs itself (about a minute, with a one-line message). Every other time, it goes straight to building the email.

When it finishes, the window says **"Done. Your email draft should now be open."** and your usual email app pops up with the newsletter already in the body.

### Step 5 — Pick recipients and send

What you see depends on which email app your computer is set up to use by default — the toolkit detected this automatically:

- **If your default is Microsoft Outlook (desktop):** Outlook pops up a new draft message. The newsletter is already in the body and the subject line is filled in. **You only have to type the recipients in the To: field and click Send.**

- **If your default is Apple Mail, Thunderbird, Gmail in your browser, or anything else:** the toolkit copied the formatted newsletter to your clipboard and opened a new blank message in your usual email app, with the subject line filled in. Click in the message body, press `Ctrl+V` (or `⌘+V` on macOS) to paste the newsletter, type the recipients, and click Send.

That's it!

> **Tip:** if the wrong email app shows up or Outlook doesn't open, see "Common questions" below.

---

## Common questions

**❓ I double-clicked the launcher but nothing happens / it flashes and closes.**
Two common causes:
- **Python isn't installed yet.** Run the launcher again from the command window so you can read the error: open the project folder, click in the address bar, type `cmd`, press Enter, then type `"Make Newsletter.bat"` and press Enter. If it complains about Python, install Python (see Setup step 2).
- **macOS only:** macOS may need a one-time permission. Open Terminal in the project folder and run `chmod +x "Make Newsletter.command"`. Then double-click again.

**❓ The launcher says "ERROR: file not found".**
Your filled-in Word file isn't in the project folder. Move (or save) `issue-3.docx` (or whatever you named it) into the same folder as `Make Newsletter.bat`. Then re-run the launcher.

**❓ I don't see the Dean photo or the logo in the preview.**
Make sure you used the launcher (or ran the full `all` command) — that step also publishes the photos to the web. If they still don't show, try refreshing your browser.

**❓ The preview shows a broken-image icon where one of my photos should be.**
Most likely the photos haven't been pushed to the public web yet. Re-run the launcher — it always re-uploads photos. Refresh the preview.

**❓ I need to redo issue 3 — what do I do?**
Just double-click the launcher again and enter `3` when asked. It will overwrite the previous output. No harm done.

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

**The everyday way:** double-click `Make Newsletter.bat` (Windows) or `Make Newsletter.command` (macOS). Answer the two prompts. Done.

**The advanced way** — if you prefer typing commands yourself:

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
| `Make Newsletter.bat` (Windows), `Make Newsletter.command` (macOS) | **Double-click this.** The everyday launcher. |
| `Meridian_Newsletter_Template.docx` | **The template you fill in.** Open in Word. |
| `drop-images/` | Optional folder for batch-adding photos by filename. |
| `dist/` | The finished email files end up here. |
| `assets/` | Where uploaded photos are kept. |
| `images/` | Permanent images (school logo, Dean photo). |
| `NagoyaU_MedSchool_Newsletter_Template-2.docx` | Original template, kept as reference. |
| `build_newsletter.py`, `scripts/`, `templates/`, `tests/`, `requirements.txt` | The toolkit's machinery. **Don't touch.** |

---

## For developers

Technical details for whoever maintains the toolkit:

- **Stack:** Python 3.12, `python-docx`, `Jinja2`, `css_inline`, `click`, `pytest`.
- **Visual identity:** primary `#8B1A1F` (NU wine red), accent `#C9A96E` (warm gold), text `#1C1C1E`, muted `#6B6B70`, cream `#F7F2EA`. Cambria headings, Calibri body.
- **Email-client compatibility:** 600px table-based layout, inline CSS via `css_inline`, MSO conditional ghost tables for Outlook desktop, `meta color-scheme` for dark-mode best effort. Validator emits warning if rendered HTML exceeds Gmail's 102 KB clip threshold.
- **Module map:** `scripts/build_template.py` (DOCX builder) · `scripts/docx_parser.py` (DOCX → `Newsletter` dataclass) · `scripts/image_handler.py` (embedded + drop-folder, GitHub raw URL builder) · `scripts/renderer.py` + `templates/*.j2` (Jinja2 → HTML) · `scripts/inliner.py` (`css_inline`) · `scripts/validator.py` (HEAD checks + size warning) · `scripts/publisher.py` (git add/commit/push of `assets/issue-N/`) · `scripts/oxml_helpers.py` (raw OXML for shading, borders, fields).
- **Constraints:** section names and content are not edited by the script — only the visual style is. Nested tables in DOCX are unsupported. Drop-image regex: `^s(?P<section>\d+)_(?P<order>\d+)_(?P<slug>[a-z0-9-]+)\.(jpg|jpeg|png|webp|gif)$`.
- **Tests:** `python -m pytest tests/ --cov=scripts` — pure-logic modules (parser, image handler, renderer, inliner, validator, composer) are well covered; `build_template.py`, `oxml_helpers.py`, and `publisher.py` are exercised end-to-end via the smoke build rather than unit tests.
- **Rebuild the template after design tweaks:** `python build_newsletter.py build-template`.
- **Smoke test:** `python build_newsletter.py build --input Meridian_Newsletter_Template.docx --issue 0 --no-remote-check`.
