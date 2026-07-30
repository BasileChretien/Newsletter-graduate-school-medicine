# MERIDIAN — The Newsletter Toolkit

[![tests](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/actions/workflows/tests.yml/badge.svg)](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![tests: 378 passing](https://img.shields.io/badge/tests-378%20passing-brightgreen.svg)](tests/)
[![release: v1.0.1](https://img.shields.io/github/v/release/BasileChretien/Newsletter-graduate-school-medicine)](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/releases/latest)

> 🇯🇵 [日本語版はこちら](README.ja.md)

> **MERIDIAN** — *Where medicine meets the world.*

> **One Word file → one polished email → one Outlook draft.** No copy-paste. No broken images. No formatting falling apart at recipients' end. Used in production at the **Graduate School of Medicine, Nagoya University** — and engineered to be forkable for any institution with the same problem.

> ⭐ **Like what you see? [Star the repo](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/stargazers)** so other institutions facing the same problem can find it. (And [open an issue](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/issues/new/choose) if you've forked it for yours — you'll get a "Used by" listing.)

## Before / after

| The old way | The MERIDIAN way |
|---|---|
| Open Word, copy section by section, paste into Outlook | Fill the Word file as usual, double-click `Make Newsletter.bat` |
| Watch the formatting fall apart in Outlook | Polished HTML email opens in Outlook with the body already populated |
| Resize and re-upload photos to a file share | Drop photos into the Word doc; the toolkit uploads them automatically |
| Realise after sending that recipients see broken images | Pre-send validation flags broken images, oversized emails, and unfilled placeholders |
| Re-type the BCC list every issue | `recipients.txt` populates BCC automatically, with separator-injection and Unicode-smuggle defences |
| Half a day per issue on plumbing | A few minutes per issue on plumbing |

> **Want to see it?** Generate a sample render yourself in 60 seconds: clone the repo, run `python build_newsletter.py build-template` (uses the bundled template + dean photo), then open the generated DOCX in Word. The HTML side is just `python build_newsletter.py build --input issue-1.docx --issue 1 --no-remote-check` after filling in any DOCX. (Working on getting a hosted preview link up — PR welcome.)

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

Primarily the editor at the Graduate School of Medicine producing the quarterly newsletter — but the toolkit is **fully forkable** for any institution with the same problem. Replace the logo + dean photo + colour palette in `scripts/config.py`, point it at your own GitHub repo, and you have a branded newsletter pipeline for your department in an afternoon. The MIT license explicitly carves out the Nagoya University trademark assets (logo, seal, "MERIDIAN" wordmark) so you don't accidentally inherit them when you fork.

**Realistic adoption fits include:**

- University departments (medicine, science, engineering, humanities) producing internal-comms newsletters.
- Hospital communication offices sending physician / staff briefings.
- Research labs or institutes with a quarterly stakeholder update.
- Academic societies / conference committees sending member announcements.
- Anywhere there's a non-technical editor + a Word draft + a "make this look professional in email without copy-pasting" gap.

**Fork it in an afternoon:** see [CONTRIBUTING.md](CONTRIBUTING.md) for the 6-step rebrand checklist. If you ship a working fork, [open a "[fork]" issue](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/issues/new?template=institution_fork.md) and we'll add you to a "Used by" list here.

## Used by

> Forks live here. If yours runs in production, [tell us about it](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/issues/new?template=institution_fork.md) and we'll list it.

- **Graduate School of Medicine, Nagoya University** — the originating fork. Quarterly newsletter, Outlook desktop, ~50-recipient BCC, Japanese + English content.

## Under the hood (for developers)

Python 3.12, `python-docx`, `Jinja2`, `css_inline` (Rust-backed), `BeautifulSoup4`, `click`, `pytest`. Outlook integration via `pywin32` COM on Windows; AppleScript / `osascript` on macOS; `xclip` / `wl-copy` on Linux. **378 tests** across 28 files covering parser, image handler, validator, plaintext converter, mail backends, the `.eml` draft builder, the browser build, security guards (NFKC + invisible-char strip on recipient validation, CSS-hidden element scrub, URL-scheme allowlist, magic-byte **and extension** gating on embedded images, decompression-bomb caps enforced on bytes written) and visual regression contracts. **29 fix bundles** across **10 specialist-review rounds** (architect, Python, security, code, visual, UX, email-deliverability) — every change has at least one regression test pinned. The current production tag is `v1.0.1-bundle29`.

You do **not** need any of the above to use the toolkit as an editor. The setup steps below are everything.

---

## Setup — do this once (about 5 minutes for Outlook users)

**Most editors send their newsletter from Microsoft Outlook on Windows.** That's the default flow, and it's just two steps.

> 🆕 **Updated April 2026:** one-click ZIP download is now the recommended flow for Outlook editors. Photos travel inside the email itself, so no GitHub URL — and no GitHub account — is needed. (Earlier versions of this README warned against ZIP; that warning no longer applies if you're on Outlook desktop.)

> **Not sure if Outlook is your default?** You can skip this section entirely, run the launcher (Step 4 of *"How to make a newsletter"* below), and it will tell you which mail app it detected. Come back here only if it isn't Outlook.

### Step 1 — Download the toolkit

The fastest way:

> ### 👉 [**Click here to download the toolkit (ZIP)**](https://github.com/BasileChretien/Newsletter-graduate-school-medicine/archive/refs/heads/main.zip) 👈
>
> The download starts immediately — no GitHub login, no menus to navigate.

> **Link not working, or want to see the GitHub page first?** Open <https://github.com/BasileChretien/Newsletter-graduate-school-medicine>, click the green **Code** button (top right of the file list), then click **Download ZIP** in the dropdown. You end up with the same file. *(Forks whose default branch is something other than `main` should use this route — the one-click link above hard-codes the `main` branch.)*

Then extract it. Detailed steps, because "extract a ZIP" trips up more first-time users than any other step:

1. Click the download link above. Your browser saves a file called `Newsletter-graduate-school-medicine-main.zip` to your **Downloads** folder.
2. Open the **Downloads** folder (Windows: *File Explorer → Downloads*; macOS: *Finder → Downloads*).
3. **Right-click** the ZIP file and choose **Extract All…** (Windows) / **double-click** to extract it (macOS).
4. On Windows, change the destination from the default to **Documents**, then click **Extract**. On macOS the extracted folder lands next to the ZIP — drag it into **Documents** afterwards.
5. You now have a folder called **`Newsletter-graduate-school-medicine-main`** inside Documents. The trailing `-main` is normal — it's not a sign anything went wrong. **That folder is what you use for every newsletter from now on.**

> ⚠️ **Don't run the launcher from inside the ZIP preview window.** On Windows, double-clicking *into* the ZIP shows the files but they're still compressed; the launcher can't write photos from there. Always extract first, then open the extracted folder.

### Step 2 — Install Python

Python is the program that runs the toolkit.

- **Windows:** download the installer from <https://www.python.org/downloads/> and run it. **Important:** on the first screen, **check the box "Add Python to PATH"** before you click *Install Now*.
- **macOS:** Macs ship with Python preinstalled, so you usually have nothing to do here. If the launcher later complains about a missing Python, come back and install from <https://www.python.org/downloads/> the same way as Windows.

**That's it.** No GitHub account, no GitHub Desktop, no waiting for a write-access grant. Photos will travel inside the email itself when you send via Outlook (no public hosting needed).

> **Hospital PC where you can't install software?** Installing Python (Step 2) needs admin rights. If your IT department restricts installations, **send IT this README link** and ask them to install Python 3.12 with the **"Add Python to PATH"** option ticked. Nothing else needs admin.

### Updating the toolkit (later)

When a new version ships (e.g. *"v1.2 fixes the broken-image bug"*), upgrading is a 60-second job:

1. Delete (or rename for safety) your old `Newsletter-graduate-school-medicine-main` folder.
2. Repeat **Step 1** above to download a fresh ZIP.
3. If you keep your `recipients.txt` and your past `issue-*.docx` files **inside** the toolkit folder, copy them into the new folder before deleting the old one. (Tip: keep them in *Documents* alongside the toolkit folder instead, so upgrades never touch them.)

A ZIP is a one-time snapshot — it does not auto-update. Editors who want one-click updates instead can follow the longer "GitHub Desktop" flow below.

<details>
<summary><strong>Longer setup — for Apple Mail / Gmail-in-browser / Thunderbird editors</strong> (click to expand)</summary>

If your default mail client isn't Outlook desktop, the toolkit can still work — but it has to host the photos at a public URL because clipboards can't carry attached files. That requires a GitHub account and the longer setup flow below.

#### Step 1 — Create a free GitHub account

1. Go to <https://github.com/signup>.
2. Pick a username, type your email, choose a password, and finish the sign-up.
3. **Send your GitHub username** to the toolkit administrator so they can give you write access to the repository. Confirmation is usually within one working day; ping the administrator on Teams if it takes longer. **You can't move on to Step 2 until they confirm.**

> **What is GitHub?** It's the public host where the toolkit's photos live (only when you're not on Outlook desktop). Your account gives you permission to upload them. You don't need to learn how GitHub works — the toolkit does everything for you.

#### Step 2 — Install GitHub Desktop

1. Go to <https://desktop.github.com> and click **Download for Windows** (or **macOS**).
2. Run the installer. Default settings are fine.
3. When GitHub Desktop opens, click **Sign in to GitHub.com**. Your web browser will open and ask you to authorize GitHub Desktop. Click **Authorize**. The browser will hand control back to GitHub Desktop automatically — return to that window.

#### Step 3 — Download (clone) the toolkit

1. In GitHub Desktop, click the menu **File → Clone repository…**
2. Click the **URL** tab, then paste this address:
   ```
   https://github.com/BasileChretien/Newsletter-graduate-school-medicine.git
   ```
3. Under **Local path**, click **Choose…** and pick **Documents** (or any folder you'll remember).
4. Click **Clone**. After a few seconds you'll have a folder called `Newsletter-graduate-school-medicine` on your PC. **That's the folder you'll use for every newsletter.**

#### Step 4 — Install Python

Same as the short flow above (Windows: PATH checkbox; macOS: try the launcher first).

That's the longer setup. **You will never have to do these steps again.**

</details>

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

> **How photos travel — and what that means for you.**
>
> **Default flow (Outlook desktop) — photos are NOT hosted online.** Photos are attached **inside each email itself** as MIME attachments. They go directly from your PC to each recipient's mailbox; they never touch a public URL, GitHub, or any third-party server. **There is no online copy you can link to after sending.**
>
> Practical implications of the default flow:
>
> - ✅ **Privacy:** photos never reach the public internet. Nothing is indexed, cached, or scraped. If you delete the sent email, the only remaining copies are in each recipient's mailbox.
> - ✅ **No GitHub account, no public hosting setup.** Editors don't need any external service.
> - ✅ **Survives forwarding** in most clients — when a recipient forwards the email, the embedded photos travel along (Outlook, Apple Mail, Thunderbird preserve them; some webmail clients re-encode).
> - ⚠️ **Larger emails.** Each recipient gets a full copy of the photos. A 5-photo issue at ~500 KB each is a ~2.5 MB email **per recipient**. With a 50-recipient BCC, that's ~125 MB of mail-server bandwidth per send. University mail servers handle this fine, but be aware. Mailbox storage on the recipient's side also fills faster.
> - ⚠️ **No archive URL.** You cannot share a "see the newsletter at this link" address — there is no link. If a recipient asks for the issue six months later, you forward the original email (or send them `dist/issue-N.html` as an attachment).
> - ⚠️ **Aggressive corporate mail gateways** sometimes strip all attachments at the recipient's end (Mimecast, Proofpoint with conservative policies). The recipient sees the text but not the photos. That's a policy issue at their end, not something the toolkit can work around — see the FAQ at the bottom of this README.
> - ⚠️ **Email-size limits.** Most institutional mail servers cap a single message at 25 MB (some 10 MB). If you attach 30+ large photos in one issue, the send may fail. The toolkit caps individual photos at 2 MB pre-attachment to keep typical issues comfortably under the limit; for an unusually photo-heavy issue, prefer the URL-hosted path below.
>
> **Alternate flow (Apple Mail / Gmail-in-browser / Thunderbird).** The toolkit uploads photos to **public** GitHub URLs (`raw.githubusercontent.com/...`) and the email contains `<img src="...">` references that recipients' clients fetch on display. In that case photos **stay on GitHub permanently** (you can `git rm` them later, but old commits keep historical copies). This is the longer-setup path described above (it requires a GitHub account).
>
> **Whichever path you're on, treat photos as you would for any institutional email — don't paste in patient images or identifiable faces without written consent.**

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

> ⚠️ **First time only — your computer will warn you. This is expected, not a problem.**
>
> - **Windows** shows a blue full-screen warning: *"Windows protected your PC."* Click **More info → Run anyway**. This appears because the launcher is a small script (not a signed commercial app); Windows shows this dialog for every script downloaded from the internet, regardless of what's in it. Once you click "Run anyway" once, Windows remembers and won't ask again for this file.
> - **macOS** may show: *"Apple cannot check it for malicious software."* Click **OK** to dismiss, then **right-click** the file → **Open** → click **Open** in the smaller dialog that follows. Same logic as Windows: macOS does this for every unsigned script. After you confirm once, it stops asking. (If macOS refuses entirely, open Terminal in the folder and run `chmod +x "Make Newsletter.command"` once, then double-click again.)
>
> **Why doesn't the launcher just sign itself to skip this?** Code-signing requires a paid developer certificate ($100–500/year) for each operating system, plus a separate certificate per institution that forks the toolkit. For a tool that runs once a quarter, the click-through is the better trade-off. We may revisit this when adoption grows. Either way: the launcher source is plain text in this repo — feel free to read `Make Newsletter.bat` / `Make Newsletter.command` before running.

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
By default, in the `dist/` folder **next to the toolkit**. For issue 3, it's `dist/issue-3.html`. You can open it any time by double-clicking it.

**Want to save somewhere else** (e.g. `~/Documents/Newsletters/`)? Pass `--output-dir`:

```
python build_newsletter.py all --input issue-3.docx --issue 3 --output-dir ~/Documents/Newsletters
```

The launcher (`Make Newsletter.bat` / `.command`) auto-detects when the toolkit folder is read-only (this happens on macOS when the launcher is run from `Downloads`) and prompts you for an output location — defaulting to `~/Documents/Meridian-Newsletter/`. You can also set `MERIDIAN_OUTPUT_DIR` as an environment variable to apply the same redirect for every run.

> **One small caveat for the Outlook (CID) path:** the saved `dist/issue-N.html` references photos by their `raw.githubusercontent.com` URLs (those URLs only get *populated* by the longer GitHub Desktop flow). When you send via Outlook desktop, the toolkit attaches the same photos to the email itself — the recipient sees them fine — but if you double-click `dist/issue-N.html` later for a quick preview, the images may show as broken. **The Outlook draft is the source of truth in CID mode**; the `dist/` HTML is mainly for archival inspection by the maintainer.

**❓ My email opened blank / nothing showed up in the body.**
If you used **the bundled MERIDIAN template**, this shouldn't happen — please report it. If you used **your own Word file**, the most likely cause is that your headings don't match the patterns the toolkit recognises (`1. Title`, `Section 1: Title`, or `第1章 Title`). Since v1.1.2 the toolkit handles non-template documents by treating the whole body as one section — check the launcher's console output for a line starting *"No numbered section headings detected ... Falling back to lenient parse"*. If your DOCX is truly empty (or password-protected), the launcher prints `ERROR: no content was extracted from your Word file` and stops without opening Outlook.

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
**Most editors are on Outlook desktop, so try this first.** On the Outlook path, photos travel **inside the email itself** as MIME attachments — there is no public URL for any filter to quarantine. The most likely cause of a missing image is the recipient's corporate / hospital IT stripping all attachments at the mail gateway. That's a policy issue at their end, not something the toolkit can work around. Ask the affected recipient to check with their IT team; a single forwarded reply from their IT confirming the strip is usually enough to get the policy adjusted.

<details>
<summary>If you set up the longer "GitHub Desktop" flow (Apple Mail / Gmail-in-browser / Thunderbird path)</summary>

Photos are hosted on GitHub at `raw.githubusercontent.com`. A handful of corporate / hospital mail filters quarantine that domain. Workarounds: (1) switch to Outlook desktop on a Windows PC for the send (the recommended Phase-2 default), (2) ask the developer to set up a one-time GitHub Pages mirror (same files, different network), or (3) tell affected recipients to click the broken-image icon to view it manually.

</details>

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

## Can't install anything? Build it in your browser

If you can't run the launcher — a locked-down work machine, or you're
covering one issue as a stand-in — there's a browser version that needs
no install at all:

1. Open **[the newsletter builder](https://basilechretien.github.io/Newsletter-graduate-school-medicine/)**.
2. Drop your `issue-N.docx` on it.
3. Download the `.eml` and double-click it. Outlook opens a ready-to-send
   draft with the subject, the BCC list and the photos already in place.
   Add the To: address and press Send.

**Your Word file is never uploaded.** The page has no server behind it —
your document is read and converted inside your own browser tab, and the
BCC addresses you type go only into the draft file you download.

Two caveats: the first load takes about ten seconds (it fetches the
engine, then caches it), and Apple Mail opens `.eml` files read-only,
so on a Mac the desktop launcher is still the better route.

Deploying it for your own institution: see [`web/README.md`](web/README.md).

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
| `web/` | The no-install browser version. See [`web/README.md`](web/README.md). |
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
  - `scripts/mail/` — backend package with `MailBackend` Protocol; `OutlookBackend` (Windows COM), `EmlBackend` (writes an RFC 5322 `.eml` draft; explicit `--backend=eml` only), `ClipboardMailtoBackend` (universal fallback). Add backends by appending to `_BACKENDS` in `__init__.py`; declare `supports_inline_images` so the CID feasibility check stays correct.
  - `scripts/webapp.py` — the pipeline as one pure function (`build_from_bytes`), with no click / OS / mail-client coupling. Used by the browser build and reusable from a server or notebook.
  - `scripts/recipients.py` — `recipients.txt` reader with RFC-5322 + injection guard.
  - `scripts/i18n.py` — `tomllib` locale loader (`en` + `ja`).
  - `scripts/oxml_helpers.py` — raw OXML for shading, borders, fields, fixed table layout.
- **Repo coordinates:** `scripts.config.get_default_repo()` resolves lazily from (1) `MERIDIAN_REPO_USER`/`_NAME`/`_BRANCH` env vars → (2) `git remote get-url origin` → (3) hard-coded fallback. Forks and renames "just work".
- **Locale override:** `MERIDIAN_LOCALE=ja` for explicit Japanese; otherwise launchers detect system locale.
- **Constraints:** section names and content are not edited by the script — only the visual style is. Nested tables in DOCX are unsupported. Drop-image regex: `^s(?P<section>\d+)_(?P<order>\d+)_(?P<slug>[a-z0-9-]+)\.(jpg|jpeg|png|webp|gif)$`.
- **Tests:** `python -m pytest tests/ --cov=scripts` — pure-logic modules (parser, image handler, renderer, inliner, validator, mail, manifest, recipients, i18n) are well covered; `build_template.py`, `oxml_helpers.py`, and `publisher.py` are exercised end-to-end via the smoke build rather than unit tests.
- **Rebuild the template after design tweaks:** `python build_newsletter.py build-template`.
- **Smoke test:** `python build_newsletter.py build --input Meridian_Newsletter_Template.docx --issue 0 --no-remote-check`.
