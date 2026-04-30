@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Make Newsletter - Meridian

REM ---------------------------------------------------------------------
REM   IMPORTANT: this .bat file is ASCII-only on purpose.
REM   Windows cmd.exe parses batch files using the OEM codepage (cp932
REM   on Japanese systems) -- if we put Japanese characters here, cmd
REM   reads them as garbage BEFORE `chcp 65001` takes effect, splits
REM   strings at random bytes, and emits stray fragments as bogus
REM   "command not recognized" errors.
REM   Japanese editors get a localized experience via README.ja.md and
REM   the Python output. The launcher itself stays English to avoid
REM   any encoding confusion on Japanese Windows.
REM ---------------------------------------------------------------------

echo.
echo ================================================
echo   MERIDIAN  -  Newsletter Builder
echo ================================================
echo.

REM 0. First-run welcome -----------------------------------------------------
REM Detect first run via a marker file. If the editor just clicked through
REM Windows SmartScreen ("Windows protected your PC"), they're going to want
REM reassurance that it was supposed to do that. Print the welcome ONCE.
REM .meridian_first_run is gitignored so it doesn't pollute the repo.
if not exist ".meridian_first_run" (
    echo  Welcome to MERIDIAN -- this is your first run.
    echo.
    echo  If Windows showed a "Windows protected your PC" warning
    echo  before this window opened, that's expected. The launcher
    echo  is a small script, not a signed commercial app, so Windows
    echo  warns about it the same way it warns about every script
    echo  downloaded from the internet -- regardless of what's in it.
    echo.
    echo  Windows now remembers your "Run anyway" choice for this
    echo  file; you won't see the warning again on this launcher.
    echo  This welcome message also won't reappear after this run.
    echo.
    echo ================================================
    echo.
    > ".meridian_first_run" echo first-run completed
)

REM 1. Python check ---------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not on PATH.
    echo.
    echo  Install Python from https://www.python.org/downloads/
    echo  On the first install screen, tick "Add Python to PATH".
    echo  Then re-run this launcher.
    echo.
    pause
    exit /b 1
)

REM 2a. Setup self-check (Phase 2: downgraded from hard-fail to note) -------
REM Pre-Phase-2, the toolkit always pushed photos to GitHub before the
REM email was sent ("publish-images" step). That required the folder to
REM be a git checkout, so the launcher hard-failed on ZIP-extracted
REM copies.
REM
REM Phase 2 default is CID image mode for Outlook (the most common case
REM for the originating editor): photos travel inside the email itself
REM as MIME attachments. No GitHub publishing needed -> no git checkout
REM required. The .bat launcher can't reliably detect Outlook before
REM Python is invoked, so we just print a NOTE on ZIP-extracted folders
REM and let the build proceed; if the editor turns out to be on a
REM non-Outlook backend (which forces URL mode), the publish-images
REM step will fail later with a clearer error.
if not exist ".git" (
    echo  Note: this folder is not a git checkout (probably extracted
    echo  from ZIP).
    echo.
    echo  - If your default email app is **Outlook desktop** (the most
    echo    common case): you're fine to continue. Photos will travel
    echo    inside the email itself; no GitHub publishing is needed.
    echo  - If your default email app is **Apple Mail / Gmail in a
    echo    browser / Thunderbird**: you'll need a git checkout for
    echo    photos to reach recipients. Re-clone via GitHub Desktop
    echo    (README Step 3) before sending an issue with photos.
    echo.
    echo  You can also force URL mode explicitly with --image-mode=url
    echo  (advanced; CLI users only).
    echo.
)

REM 2b. Dependency check (install on first run) ------------------------------
python -c "import docx, jinja2, click, css_inline" >nul 2>&1
if errorlevel 1 (
    echo ================================================
    echo  FIRST-TIME SETUP IN PROGRESS
    echo ================================================
    echo  Installing toolkit dependencies. This takes 1-2 minutes;
    echo  it may look frozen for a while -- please wait, and don't
    echo  close this window.
    echo ================================================
    echo.
    python -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERROR: Could not install dependencies.
        echo  Please run:  python -m pip install -r requirements.txt
        echo  in a command window inside this folder, then re-run.
        pause
        exit /b 1
    )
    echo.
    echo Setup complete. (You will not see this message again.)
    echo.
)

REM 3. Prompts ---------------------------------------------------------------
set "ISSUE="
set /p "ISSUE=Issue number (e.g. 3): "
if "!ISSUE!"=="" (
    echo.
    echo  No issue number entered -- exiting.
    pause
    exit /b 1
)
echo !ISSUE!| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo.
    echo  ERROR: "!ISSUE!" is not a valid issue number.
    echo  Please enter a positive integer like 3 or 12.
    pause
    exit /b 1
)

set "DEFAULT_DOCX=issue-!ISSUE!.docx"
set "DOCX="
if exist "!DEFAULT_DOCX!" (
    set /p "DOCX=Word file [!DEFAULT_DOCX!]: "
    if "!DOCX!"=="" set "DOCX=!DEFAULT_DOCX!"
) else (
    set /p "DOCX=Word file name (e.g. issue-!ISSUE!.docx): "
)

if "!DOCX!"=="" (
    echo.
    echo  No file name entered -- exiting.
    pause
    exit /b 1
)

if not exist "!DOCX!" (
    echo.
    echo  ERROR: file not found:  !DOCX!
    echo  Make sure your filled-in Word file is in this folder:
    echo    %CD%
    pause
    exit /b 1
)

REM 4. Run the pipeline ------------------------------------------------------
echo.
echo Building issue !ISSUE! from !DOCX! ...
echo.
python build_newsletter.py all --input "!DOCX!" --issue !ISSUE!
set "RC=!errorlevel!"

echo.
echo ================================================
if "!RC!"=="0" (
    echo  Done. Your email draft should now be open.
    echo.
    echo  IMPORTANT: nothing has been sent yet.
    echo  Add recipients in the To: field, review,
    echo  then click Send yourself.
    echo.
    echo  Tip: copy recipients.example.txt to recipients.txt
    echo  to skip typing the recipient list next issue.
) else (
    echo  Something went wrong. See the messages above.
)
echo ================================================
echo.
pause
endlocal
