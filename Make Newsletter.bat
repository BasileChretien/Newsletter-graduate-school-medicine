@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul
title Make Newsletter - Meridian

echo.
echo ================================================
echo   MERIDIAN  -  Newsletter Builder
echo   メリディアン  -  ニュースレター作成ツール
echo ================================================
echo.

REM 1. Python check ---------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python is not installed or not on PATH.
    echo  エラー: Python がインストールされていないか、PATH に登録されていません。
    echo.
    echo  - Install Python from https://www.python.org/downloads/
    echo    https://www.python.org/downloads/ から Python をインストールしてください。
    echo  - On the first install screen, tick "Add Python to PATH".
    echo    最初の画面で「Add Python to PATH」のチェックを入れてください。
    echo  - Then re-run this launcher.
    echo    その後、このランチャーをもう一度実行してください。
    echo.
    pause
    exit /b 1
)

REM 2. Dependency check (install on first run) ------------------------------
python -c "import docx, jinja2, click, css_inline" >nul 2>&1
if errorlevel 1 (
    echo ================================================
    echo  FIRST-TIME SETUP IN PROGRESS
    echo  初回セットアップを実行中
    echo ================================================
    echo  Installing toolkit dependencies. This takes
    echo  about 1-2 minutes. You only see this once.
    echo  ツールの依存関係をインストールしています。
    echo  1〜2分かかります。表示されるのはこの一度だけです。
    echo.
    echo  *** PLEASE DO NOT CLOSE THIS WINDOW ***
    echo  *** このウィンドウを閉じないでください ***
    echo  Even if it looks frozen for up to 2 minutes,
    echo  it is still working. Just wait.
    echo  最大2分間、固まっているように見える場合があります。
    echo  正常に動作中ですので、そのままお待ちください。
    echo ================================================
    echo.
    python -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  ERROR: Could not install dependencies.
        echo  エラー: 依存関係のインストールに失敗しました。
        echo  Please run:  python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo.
    echo Setup complete. (You will not see this message again.)
    echo セットアップ完了。(このメッセージは次回以降表示されません)
    echo.
)

REM 3. Prompts ---------------------------------------------------------------
set "ISSUE="
set /p "ISSUE=Issue number / 号数 (e.g. 3): "
if "!ISSUE!"=="" (
    echo.
    echo  No issue number entered -- exiting.
    echo  号数が入力されていません。終了します。
    pause
    exit /b 1
)
echo !ISSUE! | findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo.
    echo  ERROR: "!ISSUE!" is not a valid issue number.
    echo  エラー: 有効な号数ではありません。
    echo  Please enter a positive integer like 3 or 12.
    echo  3 や 12 のような正の整数を入力してください。
    pause
    exit /b 1
)

set "DEFAULT_DOCX=issue-!ISSUE!.docx"
set "DOCX="
if exist "!DEFAULT_DOCX!" (
    set /p "DOCX=Word file / Wordファイル [!DEFAULT_DOCX!]: "
    if "!DOCX!"=="" set "DOCX=!DEFAULT_DOCX!"
) else (
    set /p "DOCX=Word file name / Wordファイル名 (e.g. issue-!ISSUE!.docx): "
)

if "!DOCX!"=="" (
    echo.
    echo  No file name entered -- exiting.
    echo  ファイル名が入力されていません。終了します。
    pause
    exit /b 1
)

if not exist "!DOCX!" (
    echo.
    echo  ERROR: file not found:  !DOCX!
    echo  エラー: ファイルが見つかりません:  !DOCX!
    echo  Make sure your filled-in Word file is in this folder:
    echo  Word ファイルがこのフォルダにあることを確認してください:
    echo    %CD%
    pause
    exit /b 1
)

REM 4. Run the pipeline ------------------------------------------------------
echo.
echo Building issue !ISSUE! from !DOCX! ...
echo 第 !ISSUE! 号を !DOCX! から作成中...
echo.
python build_newsletter.py all --input "!DOCX!" --issue !ISSUE!
set "RC=!errorlevel!"

echo.
echo ================================================
if "!RC!"=="0" (
    echo  Done. Your email draft should now be open.
    echo  メールの下書きが開いているはずです。
    echo.
    echo  IMPORTANT: nothing has been sent yet.
    echo  Add recipients in the To: field, review,
    echo  then click Send yourself.
    echo  重要: メールはまだ送信されていません。
    echo  宛先を入力し、内容を確認してから「送信」をクリックしてください。
) else (
    echo  Something went wrong. See the messages above.
    echo  問題が発生しました。上のメッセージをご確認ください。
)
echo ================================================
echo.
pause
endlocal
