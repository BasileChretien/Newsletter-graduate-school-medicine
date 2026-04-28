@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul
title Make Newsletter - Meridian

REM Detect locale: if Windows reports a Japanese tag, switch to Japanese
REM output; otherwise English. Try the registry first (no PowerShell
REM dependency -- works on locked-down corporate machines); fall back
REM to PowerShell, then to English.
set "LANG_PREFIX="
for /f "tokens=3" %%L in ('reg query "HKCU\Control Panel\International" /v LocaleName 2^>nul ^| findstr /i "REG_SZ"') do set "LANG_PREFIX=%%L"
if "!LANG_PREFIX!"=="" (
    for /f "usebackq tokens=*" %%L in (`powershell -NoProfile -Command "(Get-Culture).Name" 2^>nul`) do set "LANG_PREFIX=%%L"
)
set "JP=0"
echo !LANG_PREFIX! | findstr /b /i "ja" >nul && set "JP=1"

if "!JP!"=="1" (
    set "BANNER=  MERIDIAN  -  ニュースレター作成ツール"
    set "PROMPT_ISSUE=号数 (例 3): "
    set "PROMPT_DOCX_DEFAULT=Wordファイル"
    set "PROMPT_DOCX_EXPLICIT=Wordファイル名"
    set "MSG_NO_PYTHON=エラー: Python がインストールされていないか、PATH に登録されていません。"
    set "MSG_NO_PYTHON_HINT=https://www.python.org/downloads/ から Python をインストールしてください。最初の画面で「Add Python to PATH」のチェックを入れてください。"
    set "MSG_SETUP_HEADING=初回セットアップを実行中"
    set "MSG_SETUP_BODY=ツールの依存関係をインストールしています。1〜2分かかります。途中で固まって見えてもそのままお待ちください。ウィンドウは閉じないでください。"
    set "MSG_DONT_CLOSE="
    set "MSG_DONT_CLOSE_BODY="
    set "MSG_SETUP_FAIL=エラー: 依存関係のインストールに失敗しました。"
    set "MSG_SETUP_DONE=セットアップ完了。(このメッセージは次回以降表示されません)"
    set "MSG_NO_ISSUE=号数が入力されていません。終了します。"
    set "MSG_BAD_ISSUE=エラー: 有効な号数ではありません。3 や 12 のような正の整数を入力してください。"
    set "MSG_NO_FILE=ファイル名が入力されていません。終了します。"
    set "MSG_FILE_NOT_FOUND=エラー: ファイルが見つかりません:"
    set "MSG_FILE_HINT=Word ファイルがこのフォルダにあることを確認してください:"
    set "MSG_BUILD=作成中..."
    set "MSG_DONE_OK=完了。メールの下書きが開いているはずです。"
    set "MSG_DONE_NOTE=重要: メールはまだ送信されていません。宛先を入力し、内容を確認してから「送信」をクリックしてください。ヒント: 毎号同じ宛先なら recipients.example.txt を recipients.txt にコピーして編集すれば、次回以降 BCC に自動で入ります。"
    set "MSG_DONE_FAIL=問題が発生しました。上のメッセージをご確認ください。"
) else (
    set "BANNER=  MERIDIAN  -  Newsletter Builder"
    set "PROMPT_ISSUE=Issue number (e.g. 3): "
    set "PROMPT_DOCX_DEFAULT=Word file"
    set "PROMPT_DOCX_EXPLICIT=Word file name"
    set "MSG_NO_PYTHON=ERROR: Python is not installed or not on PATH."
    set "MSG_NO_PYTHON_HINT=Install Python from https://www.python.org/downloads/ and tick \"Add Python to PATH\" on the first install screen."
    set "MSG_SETUP_HEADING=FIRST-TIME SETUP IN PROGRESS"
    set "MSG_SETUP_BODY=Installing toolkit dependencies. This takes 1-2 minutes; it may look frozen for a while -- please wait, and don't close this window."
    set "MSG_DONT_CLOSE="
    set "MSG_DONT_CLOSE_BODY="
    set "MSG_SETUP_FAIL=ERROR: Could not install dependencies."
    set "MSG_SETUP_DONE=Setup complete. (You will not see this message again.)"
    set "MSG_NO_ISSUE=No issue number entered -- exiting."
    set "MSG_BAD_ISSUE=ERROR: not a valid issue number. Please enter a positive integer like 3 or 12."
    set "MSG_NO_FILE=No file name entered -- exiting."
    set "MSG_FILE_NOT_FOUND=ERROR: file not found:"
    set "MSG_FILE_HINT=Make sure your filled-in Word file is in this folder:"
    set "MSG_BUILD=Building..."
    set "MSG_DONE_OK=Done. Your email draft should now be open."
    set "MSG_DONE_NOTE=IMPORTANT: nothing has been sent yet. Add recipients in the To: field, review, then click Send yourself. Tip: copy recipients.example.txt to recipients.txt to skip typing the list next issue."
    set "MSG_DONE_FAIL=Something went wrong. See the messages above."
)

echo.
echo ================================================
echo !BANNER!
echo ================================================
echo.

REM 1. Python check ---------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo  !MSG_NO_PYTHON!
    echo.
    echo  !MSG_NO_PYTHON_HINT!
    echo.
    pause
    exit /b 1
)

REM 2. Dependency check (install on first run) ------------------------------
python -c "import docx, jinja2, click, css_inline" >nul 2>&1
if errorlevel 1 (
    echo ================================================
    echo  !MSG_SETUP_HEADING!
    echo ================================================
    echo  !MSG_SETUP_BODY!
    echo ================================================
    echo.
    python -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  !MSG_SETUP_FAIL!
        pause
        exit /b 1
    )
    echo.
    echo !MSG_SETUP_DONE!
    echo.
)

REM 3. Prompts ---------------------------------------------------------------
set "ISSUE="
set /p "ISSUE=!PROMPT_ISSUE!"
if "!ISSUE!"=="" (
    echo.
    echo  !MSG_NO_ISSUE!
    pause
    exit /b 1
)
echo !ISSUE! | findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo.
    echo  !MSG_BAD_ISSUE!
    pause
    exit /b 1
)

set "DEFAULT_DOCX=issue-!ISSUE!.docx"
set "DOCX="
if exist "!DEFAULT_DOCX!" (
    set /p "DOCX=!PROMPT_DOCX_DEFAULT! [!DEFAULT_DOCX!]: "
    if "!DOCX!"=="" set "DOCX=!DEFAULT_DOCX!"
) else (
    set /p "DOCX=!PROMPT_DOCX_EXPLICIT! (e.g. issue-!ISSUE!.docx): "
)

if "!DOCX!"=="" (
    echo.
    echo  !MSG_NO_FILE!
    pause
    exit /b 1
)

if not exist "!DOCX!" (
    echo.
    echo  !MSG_FILE_NOT_FOUND!  !DOCX!
    echo  !MSG_FILE_HINT!
    echo    %CD%
    pause
    exit /b 1
)

REM 4. Run the pipeline ------------------------------------------------------
echo.
echo !MSG_BUILD!
echo.
python build_newsletter.py all --input "!DOCX!" --issue !ISSUE!
set "RC=!errorlevel!"

echo.
echo ================================================
if "!RC!"=="0" (
    echo  !MSG_DONE_OK!
    echo.
    echo  !MSG_DONE_NOTE!
) else (
    echo  !MSG_DONE_FAIL!
)
echo ================================================
echo.
pause
endlocal
