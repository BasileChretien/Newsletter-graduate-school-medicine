@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Make Newsletter - Meridian

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
    echo  - Install Python from https://www.python.org/downloads/
    echo  - On the first install screen, tick "Add Python to PATH".
    echo  - Then re-run this launcher.
    echo.
    pause
    exit /b 1
)

REM 2. Dependency check (install on first run) ------------------------------
python -c "import docx, jinja2, click, css_inline" >nul 2>&1
if errorlevel 1 (
    echo First-time setup -- installing toolkit dependencies.
    echo This takes about a minute. You only see this once.
    echo.
    python -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERROR: Could not install dependencies.
        echo  Please run:  python -m pip install -r requirements.txt
        echo  in a command window inside this folder, then re-run.
        pause
        exit /b 1
    )
    echo Setup complete.
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
    echo  Make sure your filled-in Word file is in this same folder.
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
) else (
    echo  Something went wrong. See the messages above.
)
echo ================================================
echo.
pause
endlocal
