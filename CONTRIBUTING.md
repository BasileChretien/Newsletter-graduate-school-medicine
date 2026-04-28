# Contributing to MERIDIAN

Thanks for opening this file! There are two distinct things you might want
to do, and the answer for each is different:

## I want to fork MERIDIAN for my own institution

You don't need permission, you don't need to ask. **Fork it, rebrand it,
ship it.** That's the entire point of the MIT license.

The minimum-viable rebrand takes roughly an afternoon:

1. **Fork** this repo on GitHub (top-right "Fork" button).
2. **Replace the brand assets**:
   - `images/Nagoya_University_Graduate_school_medicine_logo.jpg`
     → your institution's logo
   - `images/Nagoya_university_school_medicine_dean.jpg`
     → your dean / director / lead photo
   - `scripts/config.py` — change `PALETTE`, `TITLE`, `TAGLINE`,
     `SUBTITLE`, `DEAN_NAME`, `DEAN_NAME_PLAIN`, `DEAN_TITLE`.
3. **Replace the Word template**:
   - `NagoyaU_MedSchool_Newsletter_Template-2.docx` (the original) is the
     editable starting point.
   - Run `python build_newsletter.py build-template` to regenerate
     `Meridian_Newsletter_Template.docx` with your colours / fonts /
     dean info applied.
4. **Update the README** — change the "Why this exists" pitch and the
   institution name. Keep the structure; the 4-step setup flow has been
   tuned across 10 review rounds for non-technical editors.
5. **Update `LICENSE`** — preserve the MIT grant but change the
   trademark-exclusion clause to name *your* institution's brand assets,
   not Nagoya University's.
6. **Push to your own GitHub repo.** The toolkit auto-detects the repo
   via `git remote get-url origin`, so the raw-image URLs in your
   editors' newsletters will point at your fork automatically.

If you ship a working rebrand, **open an issue here so we can list you in
the README.** Cross-pollination is good for everyone.

## I want to improve the upstream toolkit

Issues, ideas, and pull requests are very welcome.

### Quick-start for code contributions

```bash
git clone https://github.com/BasileChretien/Newsletter-graduate-school-medicine.git
cd Newsletter-graduate-school-medicine
python -m venv .venv
. .venv/Scripts/activate    # Windows
# or: source .venv/bin/activate    # macOS/Linux
pip install -r requirements.txt
python -m pytest             # 201 tests, ~7 seconds
```

### Code conventions

- **Tests for every fix.** The toolkit has been through 10 specialist-review
  rounds; every regression and gap was pinned by at least one test in the
  bundle that fixed it. Please match that bar — a PR with only an
  implementation change is borderline; a PR with implementation + a
  regression test that would have caught the bug is welcome.
- **Type annotations on public functions.** `python-docx` types live at
  `docx.text.paragraph.Paragraph`, `docx.table.Table`, etc.
- **PEP 8 + ruff.** No tooling enforcement is wired up yet, but it's coming.
- **Keep modules under 800 lines.** When approaching, prefer a package
  split (see `scripts/build_template/` for the pattern).
- **Bilingual user-facing strings.** New error messages or README sections
  should have both an English and a Japanese version. The launcher is
  English-only by design (Windows `cmd.exe` cp932 hostility) — message
  bilingualism lives in the Python output and the READMEs.

### What I'm specifically interested in

Stars on this repo are nice but contributions that make MERIDIAN more
useful to a wider audience are nicer:

- Additional mail backends (Thunderbird XPCOM, Gmail OAuth, generic SMTP).
- More language packs in `locales/` (Korean, Chinese, French — anywhere
  with a multi-lingual academic newsletter habit).
- A `--dry-run` mode that builds the HTML + opens the preview without
  publishing photos, for iteration speed.
- Conference / society / lab-newsletter template variants under
  `templates/variants/`.
- CI that auto-builds the Outlook draft on every PR (containerised
  Wine + win32com — ambitious but possible).

### Review process

Every prior change in this repo went through a 7-axis review (architect /
Python / security / code / visual / UX / email-deliverability). For PRs I'm
not going to make you wait for 7 reviewers, but I will ask the obvious
questions per axis. Help me out by writing a PR description that addresses
them up front:

- **Architect:** does this introduce a new module / dependency? Why?
- **Python:** any new public API? Type-annotated? Tests added?
- **Security:** any new user-input boundary? How is it validated?
- **Visual:** screenshot of the rendered email, before/after.
- **UX:** what does the editor see in their CLI / launcher?
- **Email deliverability:** does it change the MIME structure, the
  plaintext alternative, or the inlined CSS? In which clients was it
  tested?

## Code of conduct

Be kind. This is an academic-newsletter toolkit, not a battlefield.

If you're not sure whether something fits — open an issue and ask. The
worst answer is "no, but here's why" and you'll have learned something.
