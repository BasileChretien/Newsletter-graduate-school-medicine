# MERIDIAN — The Newsletter Toolkit

> 🇯🇵 [日本語版はこちら](README.ja.md)

> **MERIDIAN** — *Where medicine meets the world.*

The official newsletter toolkit for the **Graduate School of Medicine, Nagoya University**.

## Why this exists

Producing a department newsletter the old way means an editor copy-pastes paragraphs from a Word draft into Outlook, watches the formatting fall apart, hand-uploads photos to a file share, and sends a message that recipients see clipped, mis-rendered, or full of broken-image icons. Every issue burns a half-day on plumbing instead of content.

**MERIDIAN replaces that workflow with one double-click.** The editor fills in the Word template like any other document. The launcher reads it, builds a polished HTML email that renders the same in Outlook, Gmail, and Apple Mail, uploads the photos to a public web address, and opens an Outlook draft with the newsletter already in the body and the BCC list already filled in. The editor types the recipients (or loads a saved list), reviews, clicks Send. Done in minutes, every issue.

## What you get

- **Fill a Word file → get a polished email.** No copy-paste. No "why is everything Times New Roman now?" The Word template is pre-styled with the official Nagoya University design system (NU blue `#003F88`, warm gold accent, Cambria headings, Calibri body); the HTML output mirrors it pixel-for-pixel where it matters and degrades gracefully where email clients force it to.
- **Real Outlook drafts, not mailto: links.** On Windows the toolkit talks directly to Outlook desktop and produces a multipart-alternative draft (HTML + plaintext) — corporate spam filters score it cleanly, and the editor never has to paste anything. On macOS it opens Apple Mail or your default client with the body on the clipboard ready to paste.
- **Photos handled for you.** Drop images into the Word file and the toolkit extracts them, names them, uploads them to GitHub, and rewrites the email to use the public URLs. Recipients see real photos, not "click to load remote content" placeholders. Need a batch instead? Drop them into `drop-images/` with a numbered filename and the toolkit slots them into the right section.
- **Multi-client by design.** 600 px table-based layout, every CSS rule inlined, Outlook ghost-tables for column survival, mso-line-height locks for 1-px gold rules, print stylesheet that swaps the cream-and-gold masthead for an ink-friendly black-and-white version. Tested across Outlook 2016+, Outlook web, Gmail web/mobile, Apple Mail macOS/iOS.
- **Validation before you embarrass yourself.** A draft with `VOL. XX` still in the masthead won't ship — the validator hard-blocks unfilled placeholder text. Long-subject warnings before recipients see truncated previews. Broken-image audit. Gmail 102 KB clip-warning. The pipeline catches the things you'd otherwise discover from a colleague's reply.
- **Bilingual JP / EN.** The README, the launcher prompts, and the error messages all ship in Japanese and English. macOS auto-detects locale.
- **No programming required.** Editors run a `Make Newsletter.bat` or `Make Newsletter.command` double-click. Two prompts: issue number, and the file name of your filled Word doc. That's it.

## Who it's for

Primarily the editor at the Graduate School of Medicine producing the quarterly newsletter — but the toolkit is **fully forkable** for any institution with the same problem. Replace the logo + dean photo + colour palette in `scripts/config.py`, point it at your own GitHub repo, and you have a branded newsletter pipeline for your department in an afternoon.

## Under the hood (for developers)

Python 3.12, `python-docx`, `Jinja2`, `css_inline` (Rust-backed), `BeautifulSoup4`, `click`, `pytest`. Outlook integration via `pywin32` COM on Windows; AppleScript / `osascript` on macOS; `xclip` / `wl-copy` on Linux. **201 tests** across 21 files covering parser, image handler, validator, plaintext converter, mail backends, security guards (NFKC + invisible-char strip on recipient validation, CSS-hidden element scrub, URL-scheme allowlist) and visual regression contracts. **29 fix bundles** across **10 specialist-review rounds** (architect, Python, security, code, visual, UX, email-deliverability) — every change has at least one regression test pinned. The current production tag is `v1.0.1-bundle29`.

You do **not** need any of the above to use the toolkit as an editor. The four setup steps below are everything.

---

## Setup — do this once (about 15 minutes)

Do all four steps in order. Don't skip any.

### Step 1 — Create a free GitHub account

1. Go to <https://github.com/signup>.
2. Pick a username, type your email, choose a password, and finish the sign-up.
3. **Send your GitHub username** to the toolkit administrator so they can give you write access to the repository (this is what lets you upload photos). The administrator usually confirms within **one business day**. **You can't move on to Step 2 until they confirm.**

> **What is GitHub?** It's just where the toolkit lives. Your account gives you permission to upload your newsletter's photos. You don't need to learn how GitHub works — the toolkit does everything for you.

> **Working on a hospital PC where you can't install software?** Steps 2 and 4 below need admin rights to install GitHub Desktop and Python. If your IT department restricts installations on your machine, **show them this README** and ask them to install both for you. Show them this section in particular — they will recognise the requirements.

### Step 2 — Install GitHub Desktop

1. Go to <https://desktop.github.com> and click **Download for Windows** (or **macOS**).
2. Run the installer. Default settings are fine.
3. When GitHub Desktop opens, click **Sign in to GitHub.com**. Your web browser will open and ask you to authorize GitHub Desktop. Click **Authorize**. The browser will hand control back to GitHub Desktop automatically — return to that window.

### Step 3 — Download (clone) the toolkit

1. In GitHub Desktop, click the menu **File → Clone repository…**
2. Click the **URL** tab, then paste this address:
   ```
   https://github.com/BasileChretien/Newsletter-graduate-school-medicine.git
   ```
3. Under **Local path**, click **Choose…** and pick **Documents** (or any folder you'll remember).
4. Click **Clone**. After a few seconds you'll have a folder called `Newsletter-graduate-school-medicine` on your PC. **That's the folder you'll use for every newsletter.**

> **Heads up for next time you visit the project page on github.com:** that page has a green **Code** button with a **Download ZIP** option. **Don't use it** — a ZIP copy can build the email but photos won't upload to the web, so recipients will see broken-image icons. Always come back through **GitHub Desktop** (this Step 3) instead. The launcher also detects a ZIP-extracted folder and stops with a clear error, but if you can avoid it, you'll save yourself a few minutes of "wait, why doesn't it work?".

### Step 4 — Install Python

Python is the program that runs the toolkit.

- **Windows:** download the installer from <https://www.python.org/downloads/> and run it. **Important:** on the first screen, **check the box "Add Python to PATH"** before you click *Install Now*.
- **macOS:** open **Terminal** (Applications → Utilities → Terminal), type `python3 --version`, press Enter. If you see something like `3.12.x`, you're done. Otherwise install from <https://www.python.org/downloads/> the same way as Windows.

That's the whole setup. **You will never have to do these four steps again.**

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
- **Sections are flexible.** The toolkit ships with a 7-section starter template, but you can rename, add, remove, or reorder sections however you want.
  - **To rename a section:** just edit the heading text in Word. The section number can stay the same.
  - **To add a new section:** in Word, place your cursor on a blank line where you want it, type the next number followed by a period, a space, and the title — for example `8. Special Feature: Nobel Prize Winner`. (A colon `8:` works too; so does `Section 8 — Title`.) Highlight that line and click **Heading 1** in the *Home → Styles* ribbon (or press *Ctrl+Alt+1* on Windows / *⌘+Option+1* on Mac).
  - **To remove a section:** select the heading and everything below it that belongs to that section (paragraphs, bullet lists, tables) and press **Delete**.
  - **For sub-sections** (e.g. "Notable Publications"), use Word's **Heading 2** style: select the line, then click **Heading 2** in *Home → Styles* (or press *Ctrl+Alt+2* / *⌘+Option+2*). A short bold line without a period also works as a fallback if you forget the style.

> **Don't worry about breaking the template.** Your filled-in copy is just a copy — the original `Meridian_Newsletter_Template.docx` is never touched. **If your copy gets mangled, just delete it and open the template again.** Nothing is lost.

> **The dean's name and photo are already filled in for you** (currently *Prof. Masahisa Katsuno*) — you don't need to touch the credentials block or the signature line. If the dean changes, ask the developer to update the template.

Save the file when you're done.

### Step 3 — Add photos (optional)

> ⚠️ **Privacy note:** every photo you put in the newsletter is uploaded to **public** GitHub URLs (`raw.githubusercontent.com/...`) so that recipients' email clients can load it. They stay there permanently. **Do not paste in patient photos, identifiable faces without consent, or anything you wouldn't put on a public web page.**

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

### Optional — save your distribution list

If you send the newsletter to the same group of people every issue, you can avoid typing 50 addresses every time:

1. Copy `recipients.example.txt` to a new file called `recipients.txt` (in this same folder).
2. Open `recipients.txt` in any text editor and put one email address per line.
3. From now on, when the toolkit opens the Outlook draft, it pre-fills the **BCC** field with everyone on the list.

`recipients.txt` is gitignored — it stays only on your computer, never on GitHub. To change recipients, just edit the file. Lines starting with `#` are comments.

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
Yes — go ahead. In Word, place your cursor on a blank line where you want the new section, type the next number followed by a period and a space, then the title (e.g. `8. Special Feature: Nobel Prize`). Highlight that line and click **Heading 1** in the *Home → Styles* ribbon (or press *Ctrl+Alt+1* on Windows / *⌘+Option+1* on Mac). The toolkit will pick it up automatically — no code change needed.

**❓ I want to remove a section or sub-section.**
Select the section heading (or sub-heading) and everything below it that belongs to that section — paragraphs, bullet lists, tables — and press **Delete**. The toolkit simply skips deleted sections.

**❓ I'm worried I'll break the template by editing it.**
Don't worry — your filled-in copy (`issue-3.docx`) is just a copy. The original `Meridian_Newsletter_Template.docx` is never modified. **If you mangle your copy, just delete it and open the template again** — nothing is lost.

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

**❓ Some recipients say the photos in the email are broken / missing.**
Photos are hosted on GitHub (a developer service) at `raw.githubusercontent.com`. A handful of corporate / hospital mail filters quarantine that domain and strip the images, even though the rest of the email arrives fine. If a recipient at Nagoya University reports this, ask the developer (the person who set up the toolkit for you, listed in the repo's "About" page on GitHub) to set up a one-time GitHub Pages mirror — same files, but served from `<user>.github.io/<repo>/assets/...`, which sits on a different network and is rarely flagged. Until then, an affected recipient can still click each broken-image icon to view it.

**❓ How many recipients can I BCC at once before mail is throttled?**
Most universities (including Nagoya University) cap a single outgoing message at around **50 BCC recipients**. Beyond that the message can be quietly throttled or quarantined as bulk. The toolkit doesn't enforce a limit — it BCCs whatever is in your `recipients.txt` — so it's up to you to split a > 50-person list into batches of ≤ 50. For very large lists, ask IT about a proper mailing-list address.

**❓ Will recipients' spam filters trust the email?**
Yes, as long as you send from your university account. Sending reputation depends on the mail server, not the toolkit, and `@med.nagoya-u.ac.jp` already has a trusted setup.

**❓ I printed the email and the masthead looks different from the screen.**
That's intentional. The print stylesheet swaps the dark cream-and-gold masthead for a simpler black-and-white version that doesn't drain your colour cartridge. Your recipients still see the on-screen design when they read the email — only the printed copy looks different.

---

## Quick reference card

**The everyday way:** double-click `Make Newsletter.bat` (Windows) or `Make Newsletter.command` (macOS). Answer the two prompts. Done.

<details>
<summary><strong>CLI commands (for developers / power users)</strong> — click to expand. The launcher above does all of this for you; this list is only useful if you're maintaining the toolkit or scripting around it.</summary>

| What you want to do | Type this |
|---|---|
| Make a newsletter for issue N (full routine) | `python build_newsletter.py all --input issue-N.docx --issue N` |
| Just rebuild the email without uploading | `python build_newsletter.py build --input issue-N.docx --issue N --no-remote-check` |
| Open the latest preview in your browser | `python build_newsletter.py preview --issue N` |
| Open the email draft (after a previous build) | `python build_newsletter.py compose --issue N --input issue-N.docx` |
| Re-upload only the photos | `python build_newsletter.py publish-images --issue N` |
| Check which email app the toolkit will use | `python build_newsletter.py detect-mail` |

(Replace `N` with the issue number every time.)

</details>

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

- **Stack:** Python 3.12, `python-docx`, `Jinja2`, `css_inline`, `click`, `pytest`, `pywin32` (Windows only).
- **Visual identity** (per the [Nagoya University design guideline](https://www.med.nagoya-u.ac.jp/intranet/pr/logo/)): primary `#003F88` (NU blue); accent gold `#A8864B` (AA-compliant on white) used for borders, dividers, bullet markers, section dashes; footer-link gold `#E8C97F` (brighter, on charcoal); text `#1C1C1E`; muted `#6B6B70`; cool off-white surface `#EEF2F7`; stripe `#DCE3EE`; hairline `#C9D2DE`; page background `#E6EBF2`. Cambria headings, Calibri body.
- **Email-client compatibility:** 600px table-based layout, inline CSS via `css_inline` plus a small kept-`<style>` block carrying `@media print`, dark-mode hints, and Apple-Mail data-detector overrides. MSO conditional ghost tables for Outlook desktop. `bgcolor` HTML attributes on masthead/header/footer survive Gmail iOS forced inversion. Validator: 80 KB early warning, 102 KB Gmail clip warning, broken-URL **warnings** (no longer hard errors).
- **Module map:**
  - `scripts/build_template.py` — DOCX builder, named table indices (`TABLE_*`), `_normalize_body_run()` helper.
  - `scripts/docx_parser.py` — DOCX → `Newsletter` dataclass; inline-image detection via `media://` sentinels.
  - `scripts/image_handler.py` — embedded + drop-folder, magic-bytes allowlist, raw-URL builder.
  - `scripts/renderer.py` + `templates/*.j2` — Jinja2 → HTML, highlight-card detection, `<em>` stripping.
  - `scripts/inliner.py` — `css_inline` + kept-`<style>` block.
  - `scripts/validator.py` — parallel HEAD checks (max 8 workers), placeholder regex, size + reminder warnings.
  - `scripts/publisher.py` — `git add/commit/push` of `assets/issue-N/`; 60-second subprocess timeout.
  - `scripts/manifest.py` — per-issue audit trail (DOCX SHA-256, dean info, file inventory); preserves audit data on same-hash re-builds.
  - `scripts/mail/` — backend package with `MailBackend` Protocol; `OutlookBackend` (Windows COM), `ClipboardMailtoBackend` (universal). Add backends by appending to `_BACKENDS` in `__init__.py`.
  - `scripts/recipients.py` — `recipients.txt` reader with RFC-5322 + injection guard.
  - `scripts/i18n.py` — `tomllib` locale loader (`en` + `ja`).
  - `scripts/oxml_helpers.py` — raw OXML for shading, borders, fields, fixed table layout.
- **Repo coordinates:** `scripts.config.get_default_repo()` resolves lazily from (1) `MERIDIAN_REPO_USER`/`_NAME`/`_BRANCH` env vars → (2) `git remote get-url origin` → (3) hard-coded fallback. Forks and renames "just work".
- **Locale override:** `MERIDIAN_LOCALE=ja` for explicit Japanese; otherwise launchers detect system locale.
- **Constraints:** section names and content are not edited by the script — only the visual style is. Nested tables in DOCX are unsupported. Drop-image regex: `^s(?P<section>\d+)_(?P<order>\d+)_(?P<slug>[a-z0-9-]+)\.(jpg|jpeg|png|webp|gif)$`.
- **Tests:** `python -m pytest tests/ --cov=scripts` — pure-logic modules (parser, image handler, renderer, inliner, validator, mail, manifest, recipients, i18n) are well covered; `build_template.py`, `oxml_helpers.py`, and `publisher.py` are exercised end-to-end via the smoke build rather than unit tests.
- **Rebuild the template after design tweaks:** `python build_newsletter.py build-template`.
- **Smoke test:** `python build_newsletter.py build --input Meridian_Newsletter_Template.docx --issue 0 --no-remote-check`.
