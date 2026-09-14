"""The minimum Python is stated in several places; they must agree.

`requires-python` in `pyproject.toml` is the floor, but editors never meet
it: the launchers install `requirements.txt`, which pip reads without the
project metadata, so each launcher checks the version itself. When the
floor went from 3.10 to 3.11 (3.10's end of life, 2026-10-31) these were
the places that had to move together; the next raise should fail here
until they all do.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def _floor() -> tuple[int, int]:
    match = re.search(r"""^requires-python\s*=\s*["']>=(\d+)\.(\d+)["']""",
                      _read("pyproject.toml"), re.M)
    assert match, "requires-python not found in pyproject.toml"
    return int(match.group(1)), int(match.group(2))


@pytest.mark.parametrize("launcher", ["Make Newsletter.bat",
                                      "Make Newsletter.command"])
def test_each_launcher_checks_the_requires_python_floor(launcher):
    major, minor = _floor()
    text = _read(launcher)
    assert f"sys.version_info >= ({major}, {minor})" in text
    assert f"Python {major}.{minor} or newer" in text
    assert text.count("sys.version_info >=") == 1, "one version check only"


def test_the_bilingual_launcher_names_the_floor_in_japanese_too():
    major, minor = _floor()
    assert f"Python {major}.{minor} 以上" in _read("Make Newsletter.command")


@pytest.mark.parametrize("readme, prose", [
    ("README.md", r"Python (\d+\.\d+)\+ \(CI runs"),
    ("README.ja.md", r"Python (\d+\.\d+) 以上（CI は"),
])
def test_the_readmes_state_the_same_floor(readme, prose):
    floor = "%d.%d" % _floor()
    text = _read(readme)
    badges = re.findall(r"badge/python-(\d+\.\d+)%2B", text)
    mentions = re.findall(prose, text)
    assert badges and mentions, f"{readme}: Python badge or prose not found"
    assert set(badges) == set(mentions) == {floor}, (
        f"{readme}: badge says {badges}, prose says {mentions}, "
        f"pyproject.toml says {floor}")


def test_requirements_carry_no_backport_the_floor_never_installs():
    """`tomli; python_version < "3.11"` was dead weight once 3.11 was the
    floor: no supported Python would ever install it."""
    floor = _floor()
    for line in _read("requirements.txt").splitlines():
        marker = re.search(r"""python_version\s*<\s*["'](\d+)\.(\d+)["']""", line)
        if marker:
            assert (int(marker.group(1)), int(marker.group(2))) > floor, line
