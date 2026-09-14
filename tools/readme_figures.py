"""Keep the test counts quoted in the READMEs true.

Both READMEs state the count twice: the "tests: N passing" badge and the
"Under the hood" paragraph. `tests/test_readme_figures.py` fails CI when
either disagrees with the suite; this script checks them, or rewrites
them after a green run.

Usage:
    python tools/readme_figures.py          # check
    python tools/readme_figures.py --fix    # run the suite, then rewrite
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
READMES = ("README.md", "README.ja.md")

# The CI check itself. `--fix` deselects it -- it fails, by design, while
# the figures are stale -- and counts it back in as passing, which it will
# be once they are rewritten.
SELF_CHECK = "tests/test_readme_figures.py::test_the_readmes_match_the_test_suite"

_BADGE = re.compile(
    r"(\[!\[tests: )(\d+)( passing\]\(https://img\.shields\.io/badge/tests-)"
    r"(\d+)(%20passing)")
_PROSE = {
    # **551 passing tests (2 skipped)** across 32 files
    "README.md": re.compile(
        r"(\*\*)(\d+)( passing tests \()(\d+)( skipped\)\*\* across )(\d+)( files)"),
    # テストは 32 ファイル・551 件成功（2 件スキップ）
    "README.ja.md": re.compile(
        r"(テストは )(\d+)( ファイル・)(\d+)( 件成功（)(\d+)( 件スキップ）)"),
}


@dataclass(frozen=True)
class Claim:
    """The figures one README states; None where a figure was not found."""

    file: str
    passed: int | None
    skipped: int | None
    files: int | None
    badge: int | None
    # The number in the badge IMAGE URL, which should equal its label.
    badge_image: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Counts:
    collected: int
    files: int


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    # `newline=""` keeps the file's own line endings.
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def load(repo: Path = REPO_ROOT) -> dict[str, str]:
    return {name: _read(repo / name) for name in READMES}


def read_claims(texts: dict[str, str]) -> list[Claim]:
    claims = []
    for name in READMES:
        text = texts[name]
        badge = _BADGE.search(text)
        prose = _PROSE[name].search(text)
        passed = skipped = files = None
        if prose:
            groups = prose.groups()
            if name == "README.md":
                passed, skipped, files = int(groups[1]), int(groups[3]), int(groups[5])
            else:
                files, passed, skipped = int(groups[1]), int(groups[3]), int(groups[5])
        claims.append(Claim(
            file=name, passed=passed, skipped=skipped, files=files,
            badge=int(badge.group(2)) if badge else None,
            badge_image=int(badge.group(4)) if badge else None))
    return claims


def problems(claims: list[Claim], collected: int, files: int) -> list[str]:
    """Every way the READMEs disagree with the suite, one line each."""
    found = []
    for claim in claims:
        if claim.passed is None:
            found.append(f"{claim.file}: the \"Under the hood\" test count was "
                         "not found -- was the paragraph reworded?")
        else:
            total = claim.passed + claim.skipped
            if total != collected:
                found.append(f"{claim.file}: says {claim.passed} passing + "
                             f"{claim.skipped} skipped = {total} tests; the "
                             f"suite collects {collected}")
            if claim.files != files:
                found.append(f"{claim.file}: says {claim.files} test files; "
                             f"there are {files}")
        if claim.badge is None:
            found.append(f"{claim.file}: the \"tests: N passing\" badge was not found")
        else:
            if claim.passed is not None and claim.badge != claim.passed:
                found.append(f"{claim.file}: the badge says {claim.badge} "
                             f"passing; the paragraph says {claim.passed}")
            if claim.badge_image is not None and claim.badge_image != claim.badge:
                found.append(f"{claim.file}: the badge image shows "
                             f"{claim.badge_image}; its label says {claim.badge}")
    return found


def apply_counts(texts: dict[str, str], passed: int, skipped: int,
                 files: int) -> dict[str, str]:
    """The READMEs with every figure rewritten; nothing else changes."""
    fixed = {}
    for name in READMES:
        text = _BADGE.sub(
            lambda m: f"{m.group(1)}{passed}{m.group(3)}{passed}{m.group(5)}",
            texts[name])
        if name == "README.md":
            text = _PROSE[name].sub(
                lambda m: (f"{m.group(1)}{passed}{m.group(3)}{skipped}"
                           f"{m.group(5)}{files}{m.group(7)}"), text)
        else:
            text = _PROSE[name].sub(
                lambda m: (f"{m.group(1)}{files}{m.group(3)}{passed}"
                           f"{m.group(5)}{skipped}{m.group(7)}"), text)
        fixed[name] = text
    return fixed


def parse_collected(output: str) -> int:
    """The collected total from `pytest -q --collect-only`.

    Only a line that STARTS with the count is a summary, and the last one
    wins: `--collect-only -q` prints every test id first, and an id can
    contain summary-like text -- this module's own parametrized tests
    did, which made the check read 553 for a suite of 602. A summary
    that reports collection errors is refused, because the modules that
    failed to import are missing from the count.
    """
    summaries = re.findall(r"^(\d+) tests? collected(.*)$", output, re.M)
    if not summaries:
        raise ValueError("pytest did not report how many tests it collected")
    count, rest = summaries[-1]
    if re.search(r"\d+ errors?\b", rest):
        raise ValueError(f"pytest could not collect every test module: "
                         f"{count} tests collected{rest.rstrip()}")
    return int(count)


def parse_run(output: str) -> tuple[int, int]:
    """(passed, skipped) from a pytest summary; refuses a run that was not green."""
    summaries = [line for line in output.splitlines()
                 if re.search(r"\d+ passed", line)]
    if not summaries:
        raise ValueError("no pytest summary line found")
    line = summaries[-1]
    if re.search(r"\d+ (failed|errors?)\b", line):
        raise ValueError(f"the test run was not green: {line.strip()}")
    passed = int(re.search(r"(\d+) passed", line).group(1))
    skipped = re.search(r"(\d+) skipped", line)
    return passed, int(skipped.group(1)) if skipped else 0


def count_test_files(repo: Path = REPO_ROOT) -> int:
    return len(list((repo / "tests").glob("test_*.py")))


def _pytest(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         *args, "tests"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=1800)
    return result.stdout + result.stderr


def collect(repo: Path = REPO_ROOT) -> Counts:
    """How many tests pytest collects, and how many test files there are.

    The collected total is the same on every operating system: tests that
    only run on some platforms skip at run time, not at collection.
    """
    return Counts(parse_collected(_pytest(repo, "--collect-only")),
                  count_test_files(repo))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check, or fix, the test counts quoted in the READMEs.")
    parser.add_argument("--fix", action="store_true",
                        help="run the test suite, then rewrite the figures")
    args = parser.parse_args(argv)
    texts = load(REPO_ROOT)

    if args.fix:
        passed, skipped = parse_run(_pytest(REPO_ROOT, "--deselect", SELF_CHECK))
        passed += 1   # the deselected self-check passes once this is written
        files = count_test_files(REPO_ROOT)
        fixed = apply_counts(texts, passed=passed, skipped=skipped, files=files)
        for name in READMES:
            if fixed[name] != texts[name]:
                _write(REPO_ROOT / name, fixed[name])
                print(f"{name}: {passed} passing, {skipped} skipped, {files} test files")
        remaining = problems(read_claims(fixed), collected=passed + skipped, files=files)
        for line in remaining:
            print(line)
        return 1 if remaining else 0

    counts = collect(REPO_ROOT)
    found = problems(read_claims(texts), collected=counts.collected, files=counts.files)
    for line in found:
        print(line)
    if found:
        print("\nFix with: python tools/readme_figures.py --fix")
        return 1
    print(f"README figures match the suite: {counts.collected} tests, "
          f"{counts.files} test files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
