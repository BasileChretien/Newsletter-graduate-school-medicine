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
    BANNER="  MERIDIAN  -  ニュースレター作成ツール"
    PROMPT_ISSUE="号数 (例 3): "
    PROMPT_DOCX_DEFAULT="Wordファイル"
    PROMPT_DOCX_EXPLICIT="Wordファイル名"
    MSG_NO_PYTHON="エラー: Python 3 がインストールされていません。"
    MSG_NO_PYTHON_HINT="https://www.python.org/downloads/ から Python をインストールしてください。"
    MSG_SETUP_HEADING="初回セットアップを実行中"
    MSG_SETUP_BODY="ツールの依存関係をインストールしています。1〜2分かかります。途中で固まって見えてもそのままお待ちください。ウィンドウは閉じないでください。"
    MSG_DONT_CLOSE=""
    MSG_DONT_CLOSE_BODY=""
    MSG_SETUP_FAIL="エラー: 依存関係のインストールに失敗しました。"
    MSG_SETUP_DONE="セットアップ完了。(このメッセージは次回以降表示されません)"
    MSG_NO_ISSUE="号数が入力されていません。終了します。"
    MSG_BAD_ISSUE="エラー: 有効な号数ではありません。"
    MSG_NO_FILE="ファイル名が入力されていません。終了します。"
    MSG_FILE_NOT_FOUND="エラー: ファイルが見つかりません:"
    MSG_FILE_HINT="Word ファイルがこのフォルダにあることを確認してください:"
    MSG_BUILD="作成中..."
    MSG_DONE_OK="完了。メールの下書きが開いているはずです。"
    MSG_DONE_NOTE="重要: メールはまだ送信されていません。宛先を入力し、内容を確認してから「送信」をクリックしてください。ヒント: 毎号同じ宛先なら recipients.example.txt を recipients.txt にコピーして編集すれば、次回以降 BCC に自動で入ります。"
    MSG_DONE_FAIL="問題が発生しました。上のメッセージをご確認ください。"
    PRESS_ENTER="Enter キーで閉じる..."
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
        echo "  エラー: このフォルダは git クローンではありません。"
        echo
        echo "  ZIP をダウンロード/展開した可能性があります。この状態では"
        echo "  写真が Web にアップロードされず、受信者には壊れた画像"
        echo "  アイコンが表示されてしまいます。メール下書きを作成する前に"
        echo "  設定を直すため、ここで停止します。"
        echo
        echo "  README のステップ 2 と 3 に従ってください:"
        echo "    1. https://desktop.github.com から GitHub Desktop をインストール"
        echo "    2. GitHub Desktop で File -> Clone repository をクリックし、"
        echo "       このプロジェクトを新しいフォルダに複製"
        echo "    3. 複製した新しいフォルダの中から、このランチャーを再実行"
        echo "    4. (任意) 新しい複製が動作したら、この古いフォルダは削除"
        echo "       してください。両方を残すと次回どちらをダブルクリック"
        echo "       したのか分からなくなります。"
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
        echo "       and clone this project fresh into a new folder."
        echo "    3. Re-run this launcher from inside the cloned folder."
        echo "    4. (Optional) Delete THIS folder once the new clone works"
        echo "       -- keeping both copies side-by-side will confuse you"
        echo "       next month about which launcher to double-click."
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
