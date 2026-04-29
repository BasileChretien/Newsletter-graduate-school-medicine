#!/usr/bin/env bash
# Double-clickable launcher for the MERIDIAN newsletter toolkit.
# On macOS, double-click from Finder. If macOS shows "permission denied"
# the first time, open Terminal once and run:
#     chmod +x "Make Newsletter.command"
# Then double-click again.

set -u
cd "$(dirname "$0")"

# ---- Locale detection ------------------------------------------------------
# Prefer Apple's user-locale on macOS; fall back to LANG / LC_ALL on Linux.
LANG_TAG=""
if command -v defaults >/dev/null 2>&1; then
    LANG_TAG=$(defaults read -g AppleLocale 2>/dev/null || true)
fi
[[ -z "$LANG_TAG" ]] && LANG_TAG="${LANG:-${LC_ALL:-en_US}}"

if [[ "$LANG_TAG" == ja* || "$LANG_TAG" == *_JP* ]]; then
    JP=1
else
    JP=0
fi

if [[ $JP -eq 1 ]]; then
    BANNER="  MERIDIAN — ニュースレター作成ツール"
    PROMPT_ISSUE="号数（例：3）: "
    PROMPT_DOCX_DEFAULT="Word ファイル"
    PROMPT_DOCX_EXPLICIT="Word ファイル名"
    MSG_NO_PYTHON="エラー：Python 3 がインストールされていません。"
    MSG_NO_PYTHON_HINT="https://www.python.org/downloads/ から Python をインストールしてください。"
    MSG_SETUP_HEADING="初回セットアップを実行しています"
    MSG_SETUP_BODY="ツールの依存ライブラリをインストールしています。完了まで 1〜2 分ほどかかります。処理中に画面が止まったように見える場合がありますが、そのままお待ちください。この画面は閉じないでください。"
    MSG_DONT_CLOSE=""
    MSG_DONT_CLOSE_BODY=""
    MSG_SETUP_FAIL="エラー：インストール中に問題が発生しました。インターネット接続をご確認のうえ、もう一度ダブルクリックしてみてください。それでも失敗する場合は、画面を撮影して保守担当者にお送りください。"
    MSG_SETUP_DONE="セットアップが完了しました。（このメッセージは次回以降表示されません。）"
    MSG_NO_ISSUE="号数が入力されていないため、処理を中止します。"
    MSG_BAD_ISSUE="エラー：号数の形式が正しくありません。3 や 12 のような正の整数を入力してください。"
    MSG_NO_FILE="ファイル名が入力されていないため、処理を中止します。"
    MSG_FILE_NOT_FOUND="エラー：ファイルが見つかりません："
    MSG_FILE_HINT="Word ファイルが本フォルダ内に保存されているかご確認ください："
    MSG_BUILD="作成中…"
    MSG_DONE_OK="完了しました。メールの下書きが開いていることをご確認ください。"
    MSG_DONE_NOTE="【重要】メールはまだ送信されていません。宛先をご入力のうえ、内容を確認してから、ご自身で「送信」をクリックしてください。 ※ 毎号同じ宛先に送る場合は、recipients.example.txt を recipients.txt にコピーして編集しておくと、次号以降 BCC が自動入力されます。"
    MSG_DONE_FAIL="問題が発生しました。上のメッセージをご確認ください。"
    PRESS_ENTER="Enter キーを押して閉じてください…"
else
    BANNER="  MERIDIAN  -  Newsletter Builder"
    PROMPT_ISSUE="Issue number (e.g. 3): "
    PROMPT_DOCX_DEFAULT="Word file"
    PROMPT_DOCX_EXPLICIT="Word file name"
    MSG_NO_PYTHON="ERROR: Python 3 is not installed."
    MSG_NO_PYTHON_HINT="Install from https://www.python.org/downloads/ then re-run."
    MSG_SETUP_HEADING="FIRST-TIME SETUP IN PROGRESS"
    MSG_SETUP_BODY="Installing toolkit dependencies. This takes 1-2 minutes; it may look frozen for a while -- please wait, and don't close this window."
    MSG_DONT_CLOSE=""
    MSG_DONT_CLOSE_BODY=""
    MSG_SETUP_FAIL="ERROR: Could not install dependencies."
    MSG_SETUP_DONE="Setup complete. (You will not see this message again.)"
    MSG_NO_ISSUE="No issue number entered -- exiting."
    MSG_BAD_ISSUE="ERROR: not a valid issue number. Please enter a positive integer like 3 or 12."
    MSG_NO_FILE="No file name entered -- exiting."
    MSG_FILE_NOT_FOUND="ERROR: file not found:"
    MSG_FILE_HINT="Make sure your filled-in Word file is in this folder:"
    MSG_BUILD="Building..."
    MSG_DONE_OK="Done. Your email draft should now be open."
    MSG_DONE_NOTE="IMPORTANT: nothing has been sent yet. Add recipients in the To: field, review, then click Send yourself. Tip: copy recipients.example.txt to recipients.txt to skip typing the list next issue."
    MSG_DONE_FAIL="Something went wrong. See the messages above."
    PRESS_ENTER="Press Enter to close..."
fi

echo
echo "================================================"
echo "$BANNER"
echo "================================================"
echo

# 0. First-run welcome -------------------------------------------------------
# If the editor just clicked through macOS Gatekeeper, they want to know it
# was supposed to do that. Show the welcome ONCE, then drop a marker so it
# doesn't reappear. The marker is .gitignore'd.
if [[ ! -f ".meridian_first_run" ]]; then
    if [[ $JP -eq 1 ]]; then
        echo "  ようこそ MERIDIAN へ。本ランチャーの初回起動です。"
        echo
        echo "  このウィンドウが開く前に macOS が「Apple は不正な"
        echo "  ソフトウェアでないか確認できません」と警告を表示した"
        echo "  場合、それは想定どおりの動作です。本ランチャーは"
        echo "  小さなスクリプトファイルであり、署名済みの商用"
        echo "  アプリケーションではないため、macOS は内容に関わらず"
        echo "  この種のスクリプトすべてに同じ警告を表示します。"
        echo
        echo "  macOS は今回の「開く」操作を記憶しますので、このファイル"
        echo "  に対して同じ警告が再度表示されることはありません。本歓迎"
        echo "  メッセージも次回以降は表示されません。"
    else
        echo "  Welcome to MERIDIAN -- this is your first run."
        echo
        echo "  If macOS showed an \"Apple cannot check it for"
        echo "  malicious software\" warning before this window"
        echo "  opened, that's expected. The launcher is a small"
        echo "  script, not a signed commercial app, so macOS warns"
        echo "  about it the same way it warns about every"
        echo "  unsigned script -- regardless of what's in it."
        echo
        echo "  macOS now remembers your decision; you won't see"
        echo "  the warning again on this launcher. This welcome"
        echo "  message also won't reappear after this run."
    fi
    echo
    echo "================================================"
    echo
    echo "first-run completed" > .meridian_first_run
fi

# 1. Python check ------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "  $MSG_NO_PYTHON"
    echo "  $MSG_NO_PYTHON_HINT"
    read -r -p "$PRESS_ENTER" _
    exit 1
fi

# 2a. Setup self-check -------------------------------------------------------
# A quick "is this folder set up correctly?" check before we build.
# If the editor downloaded the ZIP instead of cloning via GitHub Desktop,
# the build would succeed but photos wouldn't upload to the web -- and
# recipients would see broken-image icons. HARD-FAIL here so the editor
# fixes the setup before drafting an email (mirrors Make Newsletter.bat).
if [[ ! -d ".git" ]]; then
    if [[ $JP -eq 1 ]]; then
        echo "  お知らせ：このフォルダは GitHub Desktop でクローンされて"
        echo "  いないようです（ZIP ファイルから展開された可能性があります）。"
        echo
        echo "  この状態のままビルドはできますが、ニュースレター内の写真が"
        echo "  Web にアップロードされないため、受信者の画面では画像のリンク"
        echo "  切れアイコンが表示されてしまいます。メールの下書きを作成する"
        echo "  前に設定を整えていただくため、ここで処理を中止します。"
        echo
        echo "  以下の手順でやり直してください："
        echo "    1. https://desktop.github.com から GitHub Desktop を"
        echo "       インストールします。"
        echo "    2. GitHub Desktop の File → Clone repository から、本プロ"
        echo "       ジェクトを **新しいフォルダ** にクローンしてください"
        echo "       （例：~/Documents/Meridian-Newsletter）。"
        echo "    3. その新しいフォルダの中で、ランチャーを再実行してください。"
        echo "    4. 新しいクローンで「完了しました。メールの下書きが開いて"
        echo "       います」と表示されることを確認してから、必要に応じて古い"
        echo "       方のフォルダを削除してください。問題のあるフォルダは"
        echo "       隠しフォルダ「.git」を **持たない** 側です（正常なクローン"
        echo "       には「.git」が含まれます）。判別が難しい場合は、両方を"
        echo "       残しておいても問題ありません。"
        echo
        echo "  ご不明な点がございましたら、画面を撮影して保守担当者まで"
        echo "  お送りください。"
    else
        echo "  ERROR: this folder is not a git checkout."
        echo
        echo "  You probably extracted a ZIP. The build would succeed, but"
        echo "  photos in your newsletter would NOT upload to the web -- and"
        echo "  recipients would see broken-image icons. Aborting now so you"
        echo "  fix the setup before drafting an email."
        echo
        echo "  Please follow the README Steps 2 and 3:"
        echo "    1. Install GitHub Desktop from https://desktop.github.com"
        echo "    2. In GitHub Desktop, click File -> Clone repository"
        echo "       and clone this project fresh into a NEW folder"
        echo "       (e.g. ~/Documents/Meridian-Newsletter)."
        echo "    3. Re-run the launcher from inside that NEW folder."
        echo "    4. Once the new clone works (you see \"Done. Your email"
        echo "       draft should now be open\"), you can delete this old"
        echo "       folder. The broken folder is the one with NO hidden"
        echo "       \".git\" subfolder -- the working clone has one."
        echo "       If unsure, leave both. Keeping both is safe."
    fi
    echo
    read -r -p "$PRESS_ENTER" _
    exit 1
fi

# 2b. Dependency check -------------------------------------------------------
if ! "$PY" -c "import docx, jinja2, click, css_inline" >/dev/null 2>&1; then
    echo "================================================"
    echo " $MSG_SETUP_HEADING"
    echo "================================================"
    echo " $MSG_SETUP_BODY"
    echo "================================================"
    echo
    "$PY" -m pip install --disable-pip-version-check -r requirements.txt
    if [[ $? -ne 0 ]]; then
        echo "  $MSG_SETUP_FAIL"
        read -r -p "$PRESS_ENTER" _
        exit 1
    fi
    echo "$MSG_SETUP_DONE"
    echo
fi

# 3. Prompts -----------------------------------------------------------------
read -r -p "$PROMPT_ISSUE" ISSUE
if [[ -z "${ISSUE// /}" ]]; then
    echo "  $MSG_NO_ISSUE"
    read -r -p "$PRESS_ENTER" _
    exit 1
fi
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
    echo "  $MSG_BAD_ISSUE"
    read -r -p "$PRESS_ENTER" _
    exit 1
fi

DEFAULT_DOCX="issue-${ISSUE}.docx"
if [[ -f "$DEFAULT_DOCX" ]]; then
    read -r -p "$PROMPT_DOCX_DEFAULT [$DEFAULT_DOCX]: " DOCX
    DOCX="${DOCX:-$DEFAULT_DOCX}"
else
    read -r -p "$PROMPT_DOCX_EXPLICIT (e.g. issue-${ISSUE}.docx): " DOCX
fi

if [[ -z "${DOCX// /}" ]]; then
    echo "  $MSG_NO_FILE"
    read -r -p "$PRESS_ENTER" _
    exit 1
fi

if [[ ! -f "$DOCX" ]]; then
    echo "  $MSG_FILE_NOT_FOUND  $DOCX"
    echo "  $MSG_FILE_HINT"
    echo "    $(pwd)"
    read -r -p "$PRESS_ENTER" _
    exit 1
fi

# 4. Run ---------------------------------------------------------------------
echo
echo "$MSG_BUILD"
echo
"$PY" build_newsletter.py all --input "$DOCX" --issue "$ISSUE"
RC=$?

echo
echo "================================================"
if [[ $RC -eq 0 ]]; then
    echo "  $MSG_DONE_OK"
    echo
    echo "  $MSG_DONE_NOTE"
else
    echo "  $MSG_DONE_FAIL"
fi
echo "================================================"
echo
read -r -p "$PRESS_ENTER" _
exit $RC
