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

REM 2. Dependency check (install on first run) ------------------------------
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
