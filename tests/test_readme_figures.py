"""The test counts quoted in the READMEs must match the test suite.

Both READMEs state the count twice -- the "tests: N passing" badge and
the "Under the hood" paragraph -- and both went stale once already
(378 quoted against 551 real). `tools/readme_figures.py` reads those
figures, compares them with what pytest collects, and rewrites them with
`--fix`. The last test here is the checker itself: a pull request that
adds tests without updating the READMEs fails CI, and the failure says
which command fixes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import readme_figures as rf

REPO_ROOT = Path(__file__).resolve().parent.parent

EN = (
    "[![tests: 551 passing](https://img.shields.io/badge/tests-551%20passing"
    "-brightgreen.svg)](tests/)\n\n"
    "Linux. **551 passing tests (2 skipped)** across 32 files covering parser.\n"
)
JA = (
    "[![tests: 551 passing](https://img.shields.io/badge/tests-551%20passing"
    "-brightgreen.svg)](tests/)\n\n"
    "テストは 32 ファイル・551 件成功（2 件スキップ）で、パーサ\n"
)
READMES = {"README.md": EN, "README.ja.md": JA}


def test_reads_every_figure_from_both_readmes():
    assert rf.read_claims(READMES) == [
        rf.Claim("README.md", passed=551, skipped=2, files=32, badge=551),
        rf.Claim("README.ja.md", passed=551, skipped=2, files=32, badge=551),
    ]


def test_figures_that_match_the_suite_raise_no_problem():
    assert rf.problems(rf.read_claims(READMES), collected=553, files=32) == []


def test_stale_figures_are_named_with_both_numbers():
    problems = rf.problems(rf.read_claims(READMES), collected=560, files=33)
    assert any("553" in p and "560" in p for p in problems)
    assert any("32" in p and "33" in p for p in problems)
    assert all(p.startswith(("README.md", "README.ja.md")) for p in problems)


def test_the_badge_and_the_paragraph_must_agree():
    stale_badge = EN.replace("551 passing", "550 passing")
    problems = rf.problems(
        rf.read_claims({"README.md": stale_badge, "README.ja.md": JA}),
        collected=553, files=32)
    assert any("badge" in p and "550" in p for p in problems)


def test_a_figure_that_cannot_be_found_is_a_problem_not_a_pass():
    """Rewording the paragraph must not turn the checker into a no-op."""
    reworded = EN.replace("passing tests", "green tests")
    problems = rf.problems(
        rf.read_claims({"README.md": reworded, "README.ja.md": JA}),
        collected=553, files=32)
    assert any(p.startswith("README.md") and "not found" in p for p in problems)


def test_apply_counts_rewrites_every_figure_and_nothing_else():
    fixed = rf.apply_counts(READMES, passed=560, skipped=3, files=33)
    assert rf.read_claims(fixed) == [
        rf.Claim("README.md", passed=560, skipped=3, files=33, badge=560),
        rf.Claim("README.ja.md", passed=560, skipped=3, files=33, badge=560),
    ]
    for name, text in READMES.items():
        restored = (fixed[name].replace("560", "551").replace("33", "32")
                    .replace("（3 件", "（2 件").replace("(3 skipped)", "(2 skipped)"))
        assert restored == text


@pytest.mark.parametrize("line, expected", [
    ("553 tests collected in 1.00s", 553),
    ("1 test collected in 0.10s", 1),
    ("553 tests collected, 1 skipped in 1.00s", 553),
], ids=["plural", "singular", "with-skips"])
def test_parse_collected(line, expected):
    assert rf.parse_collected(f"...\n{line}\n") == expected


def test_parse_collected_ignores_summary_text_inside_test_ids():
    """`--collect-only -q` lists every test id before the summary, and an
    id can carry summary-like text. It did: this file's own parametrized
    ids once made the check read 553 for a suite of 602."""
    output = (
        "tests/test_x.py::test_parse[553 tests collected in 1.00s-553]\n"
        "tests/test_x.py::test_other\n"
        "\n"
        "602 tests collected in 1.26s\n"
    )
    assert rf.parse_collected(output) == 602


def test_parse_collected_refuses_collection_errors():
    """A module that fails to import is missing from the count, so the
    count cannot be trusted."""
    with pytest.raises(ValueError, match="could not collect"):
        rf.parse_collected("553 tests collected, 2 errors in 0.43s\n")


@pytest.mark.parametrize("line, expected", [
    ("551 passed, 2 skipped, 1 warning in 30.40s", (551, 2)),
    ("12 passed in 0.50s", (12, 0)),
], ids=["with-skips", "no-skips"])
def test_parse_run(line, expected):
    assert rf.parse_run(f"...\n{line}\n") == expected


def test_parse_run_refuses_a_failing_run():
    """`--fix` must never write figures from a red test run."""
    with pytest.raises(ValueError):
        rf.parse_run("1 failed, 550 passed, 2 skipped in 30.00s\n")


def test_the_readmes_match_the_test_suite():
    counts = rf.collect(REPO_ROOT)
    problems = rf.problems(rf.read_claims(rf.load(REPO_ROOT)),
                           collected=counts.collected, files=counts.files)
    assert not problems, (
        "\n".join(problems)
        + "\n\nThe READMEs quote the test count. Update them with:\n"
          "    python tools/readme_figures.py --fix")
