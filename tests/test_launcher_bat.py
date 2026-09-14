"""The Windows launcher has to parse before it can help anyone.

`cmd.exe` reads a parenthesised block -- the body of an `if (...)` -- in
one go, before running any of it, and inside a block an unescaped `)` ends
the block wherever it appears. An opening `(` in ordinary text is just
text, so it balances nothing. A friendly sentence like `echo  from ZIP).`
inside an `if` therefore closes the block early and leaves `.` behind, and
cmd stops with ". was unexpected at this time." -- right after the banner,
on every run, for every editor, whatever the `if` would have decided.

That was the state of `Make Newsletter.bat` from the Phase 2 launcher
(2026-04-30) on, unnoticed because editors had moved to the website. One
more such sentence did not crash: it silently moved the line after it out
of its block.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "Make Newsletter.bat"

_QUOTED = re.compile(r'"[^"]*"')


def _lines_inside_blocks(text: str) -> list[tuple[int, str]]:
    """(line number, stripped line) for each command inside a `( ... )` block.

    A block opens on a line whose code ends with `(` (`if ... (`,
    `) else (`) and closes on a line that starts with `)`. Quoted text is
    literal to cmd, so it is blanked before looking at the parentheses.
    """
    depth = 0
    inside = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or re.match(r"(?i)rem(\s|$)|::", line):
            continue
        code = _QUOTED.sub('""', line)
        if depth > 0 and not code.startswith(")"):
            inside.append((number, line))
        if code.startswith(")"):
            depth -= 1
        if code.endswith("("):
            depth += 1
    return inside


def _unescaped_closing_paren(line: str) -> bool:
    return bool(re.search(r"(?<!\^)\)", _QUOTED.sub('""', line)))


def test_the_launcher_is_ascii_only():
    """cmd.exe parses a batch file in the OEM codepage (cp932 on Japanese
    Windows), so a non-ASCII byte turns into stray commands."""
    LAUNCHER.read_bytes().decode("ascii")


def test_no_echo_inside_a_block_has_an_unescaped_closing_parenthesis():
    offenders = [
        f"  line {number}: {line}"
        for number, line in _lines_inside_blocks(
            LAUNCHER.read_text(encoding="ascii"))
        if re.match(r"(?i)echo\b", line) and _unescaped_closing_paren(line)
    ]
    assert not offenders, (
        "An unescaped ')' inside an if-block ends the block early, and cmd.exe "
        "then stops with '... was unexpected at this time.' Reword without "
        "parentheses, or escape it as ^):\n" + "\n".join(offenders))


def test_the_block_scanner_finds_what_it_is_looking_for():
    """Guard the guard: a scanner that found no blocks would pass anything."""
    sample = (
        'REM (a comment is not a block)\n'
        'if not exist ".git" (\n'
        '    echo  from ZIP).\n'
        '    echo  escaped^) is fine\n'
        '    set /p "X=quoted (parens) are literal: "\n'
        ') else (\n'
        '    echo.\n'
        ')\n'
        'echo (outside a block) is fine\n'
    )
    inside = _lines_inside_blocks(sample)
    assert [line for _, line in inside] == [
        "echo  from ZIP).", "echo  escaped^) is fine",
        'set /p "X=quoted (parens) are literal: "', "echo."]
    flagged = [line for _, line in inside
               if line.lower().startswith("echo") and _unescaped_closing_paren(line)]
    assert flagged == ["echo  from ZIP)."]
    # And the real launcher does have blocks for it to check.
    assert len(_lines_inside_blocks(LAUNCHER.read_text(encoding="ascii"))) > 50


@pytest.mark.skipif(
    not (sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") == "true"),
    reason="runs the real launcher through cmd.exe; CI's Windows job only")
def test_the_launcher_runs_to_its_first_prompt(tmp_path):
    """Runs the actual file, in a folder that is not a git checkout, with no
    input. It has to get past every check -- including the not-a-git-checkout
    note, the block that used to break -- and exit at the issue prompt."""
    shutil.copy(LAUNCHER, tmp_path / LAUNCHER.name)
    run = subprocess.run(
        ["cmd", "/d", "/c", LAUNCHER.name], cwd=tmp_path,
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
        errors="replace", timeout=180)
    output = run.stdout + run.stderr
    assert "was unexpected at this time" not in output, output
    assert "not a git checkout" in output, output
    assert "No issue number entered" in output, output
    assert run.returncode == 1, output
