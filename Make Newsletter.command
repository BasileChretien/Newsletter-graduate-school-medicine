#!/usr/bin/env bash
# Double-clickable launcher for the MERIDIAN newsletter toolkit.
# On macOS, double-click this file from Finder. If macOS shows a
# "permission denied" message the first time, open Terminal once and run:
#     chmod +x "Make Newsletter.command"
# Then double-click it again.

set -u
cd "$(dirname "$0")"

echo
echo "================================================"
echo "  MERIDIAN  -  Newsletter Builder"
echo "================================================"
echo

# 1. Python check ------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "  ERROR: Python 3 is not installed."
    echo
    echo "  - Install Python from https://www.python.org/downloads/"
    echo "  - Then re-run this launcher."
    echo
    read -r -p "Press Enter to close..."
    exit 1
fi

# 2. Dependency check (install on first run) ---------------------------------
if ! "$PY" -c "import docx, jinja2, click, css_inline" >/dev/null 2>&1; then
    echo "================================================"
    echo " FIRST-TIME SETUP IN PROGRESS"
    echo "================================================"
    echo " Installing toolkit dependencies. This takes"
    echo " about 1-2 minutes. You only see this once."
    echo
    echo " *** PLEASE DO NOT CLOSE THIS WINDOW ***"
    echo " Even if it looks frozen for up to 2 minutes,"
    echo " it is still working. Just wait."
    echo "================================================"
    echo
    "$PY" -m pip install --disable-pip-version-check -r requirements.txt
    if [[ $? -ne 0 ]]; then
        echo
        echo "  ERROR: Could not install dependencies."
        echo "  Please run:  $PY -m pip install -r requirements.txt"
        echo "  inside this folder, then re-run."
        read -r -p "Press Enter to close..."
        exit 1
    fi
    echo
    echo "Setup complete. (You will not see this message again.)"
    echo
fi

# 3. Prompts -----------------------------------------------------------------
read -r -p "Issue number (e.g. 3): " ISSUE
if [[ -z "${ISSUE// /}" ]]; then
    echo
    echo "  No issue number entered -- exiting."
    read -r -p "Press Enter to close..."
    exit 1
fi
# Reject anything that is not a pure positive integer.
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
    echo
    echo "  ERROR: \"$ISSUE\" is not a valid issue number."
    echo "  Please enter a positive integer like 3 or 12."
    read -r -p "Press Enter to close..."
    exit 1
fi

DEFAULT_DOCX="issue-${ISSUE}.docx"
if [[ -f "$DEFAULT_DOCX" ]]; then
    read -r -p "Word file [$DEFAULT_DOCX]: " DOCX
    DOCX="${DOCX:-$DEFAULT_DOCX}"
else
    read -r -p "Word file name (e.g. issue-${ISSUE}.docx): " DOCX
fi

if [[ -z "${DOCX// /}" ]]; then
    echo
    echo "  No file name entered -- exiting."
    read -r -p "Press Enter to close..."
    exit 1
fi

if [[ ! -f "$DOCX" ]]; then
    echo
    echo "  ERROR: file not found:  $DOCX"
    echo "  Make sure your filled-in Word file is in this same folder."
    read -r -p "Press Enter to close..."
    exit 1
fi

# 4. Run the pipeline --------------------------------------------------------
echo
echo "Building issue $ISSUE from $DOCX ..."
echo
"$PY" build_newsletter.py all --input "$DOCX" --issue "$ISSUE"
RC=$?

echo
echo "================================================"
if [[ $RC -eq 0 ]]; then
    echo "  Done. Your email draft should now be open."
else
    echo "  Something went wrong. See the messages above."
fi
echo "================================================"
echo
read -r -p "Press Enter to close..."
exit $RC
