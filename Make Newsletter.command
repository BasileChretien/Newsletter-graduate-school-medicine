#!/usr/bin/env bash
# Double-clickable launcher for the MERIDIAN newsletter toolkit.
# On macOS, double-click from Finder. If macOS shows "permission denied"
# the first time, open Terminal once and run:
#     chmod +x "Make Newsletter.command"
# Then double-click again.

set -u
cd "$(dirname "$0")"

echo
echo "================================================"
echo "  MERIDIAN  -  Newsletter Builder"
echo "  メリディアン  -  ニュースレター作成ツール"
echo "================================================"
echo

# 1. Python check ------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "  ERROR: Python 3 is not installed."
    echo "  エラー: Python 3 がインストールされていません。"
    echo
    echo "  - Install Python from https://www.python.org/downloads/"
    echo "    https://www.python.org/downloads/ から Python をインストールしてください。"
    echo "  - Then re-run this launcher."
    echo "    その後、このランチャーをもう一度実行してください。"
    echo
    read -r -p "Press Enter to close / Enter キーで閉じる..."
    exit 1
fi

# 2. Dependency check (install on first run) ---------------------------------
if ! "$PY" -c "import docx, jinja2, click, css_inline" >/dev/null 2>&1; then
    echo "================================================"
    echo " FIRST-TIME SETUP IN PROGRESS"
    echo " 初回セットアップを実行中"
    echo "================================================"
    echo " Installing toolkit dependencies. This takes"
    echo " about 1-2 minutes. You only see this once."
    echo " ツールの依存関係をインストールしています。"
    echo " 1〜2分かかります。表示されるのはこの一度だけです。"
    echo
    echo " *** PLEASE DO NOT CLOSE THIS WINDOW ***"
    echo " *** このウィンドウを閉じないでください ***"
    echo " Even if it looks frozen for up to 2 minutes,"
    echo " it is still working. Just wait."
    echo " 最大2分間、固まっているように見える場合があります。"
    echo " 正常に動作中ですので、そのままお待ちください。"
    echo "================================================"
    echo
    "$PY" -m pip install --disable-pip-version-check -r requirements.txt
    if [[ $? -ne 0 ]]; then
        echo
        echo "  ERROR: Could not install dependencies."
        echo "  エラー: 依存関係のインストールに失敗しました。"
        read -r -p "Press Enter to close..."
        exit 1
    fi
    echo
    echo "Setup complete. (You will not see this message again.)"
    echo "セットアップ完了。(このメッセージは次回以降表示されません)"
    echo
fi

# 3. Prompts -----------------------------------------------------------------
read -r -p "Issue number / 号数 (e.g. 3): " ISSUE
if [[ -z "${ISSUE// /}" ]]; then
    echo
    echo "  No issue number entered -- exiting."
    echo "  号数が入力されていません。終了します。"
    read -r -p "Press Enter to close..."
    exit 1
fi
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
    echo
    echo "  ERROR: \"$ISSUE\" is not a valid issue number."
    echo "  エラー: 有効な号数ではありません。"
    echo "  Please enter a positive integer like 3 or 12."
    echo "  3 や 12 のような正の整数を入力してください。"
    read -r -p "Press Enter to close..."
    exit 1
fi

DEFAULT_DOCX="issue-${ISSUE}.docx"
if [[ -f "$DEFAULT_DOCX" ]]; then
    read -r -p "Word file / Wordファイル [$DEFAULT_DOCX]: " DOCX
    DOCX="${DOCX:-$DEFAULT_DOCX}"
else
    read -r -p "Word file / Wordファイル名 (e.g. issue-${ISSUE}.docx): " DOCX
fi

if [[ -z "${DOCX// /}" ]]; then
    echo
    echo "  No file name entered -- exiting."
    echo "  ファイル名が入力されていません。終了します。"
    read -r -p "Press Enter to close..."
    exit 1
fi

if [[ ! -f "$DOCX" ]]; then
    echo
    echo "  ERROR: file not found:  $DOCX"
    echo "  エラー: ファイルが見つかりません:  $DOCX"
    echo "  Make sure your filled-in Word file is in this folder:"
    echo "  Word ファイルがこのフォルダにあることを確認してください:"
    echo "    $(pwd)"
    read -r -p "Press Enter to close..."
    exit 1
fi

# 4. Run the pipeline --------------------------------------------------------
echo
echo "Building issue $ISSUE from $DOCX ..."
echo "第 $ISSUE 号を $DOCX から作成中..."
echo
"$PY" build_newsletter.py all --input "$DOCX" --issue "$ISSUE"
RC=$?

echo
echo "================================================"
if [[ $RC -eq 0 ]]; then
    echo "  Done. Your email draft should now be open."
    echo "  メールの下書きが開いているはずです。"
    echo
    echo "  IMPORTANT: nothing has been sent yet."
    echo "  Add recipients in the To: field, review, then Send."
    echo "  重要: メールはまだ送信されていません。"
    echo "  宛先を入力し、内容を確認してから「送信」をクリックしてください。"
else
    echo "  Something went wrong. See the messages above."
    echo "  問題が発生しました。上のメッセージをご確認ください。"
fi
echo "================================================"
echo
read -r -p "Press Enter to close / Enter キーで閉じる..."
exit $RC
