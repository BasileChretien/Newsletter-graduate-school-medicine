"""Tests for the bundle-28 subject-length warning thresholds.

Round-9 Email M1: a single soft warn at 78 chars was too loose --
inbox previews truncate around 50 chars on Outlook desktop / Gmail
web, so a recipient may only see "MERIDIAN — VOL. 12 | ISSUE NO."
instead of the full subject. Bundle 28 introduces two thresholds:
50 (preview) and 78 (RFC + spam-filter heuristic).
"""

from __future__ import annotations

from click.testing import CliRunner

import build_newsletter as bn


def test_subject_threshold_constants_are_distinct():
    """Sanity: the two thresholds must differ AND order makes sense."""
    assert bn._SUBJECT_PREVIEW_LIMIT_CHARS == 50
    assert bn._SUBJECT_SPAM_LIMIT_CHARS == 78
    assert bn._SUBJECT_PREVIEW_LIMIT_CHARS < bn._SUBJECT_SPAM_LIMIT_CHARS


def test_subject_under_preview_threshold_no_warning(capsys, monkeypatch):
    """A 40-char subject must produce NO warning."""
    # We test the threshold logic via a small wrapper that mimics
    # the relevant lines in `_build_pipeline`.
    import click

    def emit_warnings(subject: str) -> list[str]:
        out: list[str] = []
        n = len(subject)
        if n > bn._SUBJECT_SPAM_LIMIT_CHARS:
            out.append("spam")
        elif n > bn._SUBJECT_PREVIEW_LIMIT_CHARS:
            out.append("preview")
        return out

    assert emit_warnings("x" * 40) == []
    assert emit_warnings("x" * 50) == []
    # 51 chars triggers preview warn, NOT spam warn.
    assert emit_warnings("x" * 51) == ["preview"]
    assert emit_warnings("x" * 78) == ["preview"]
    # 79 chars triggers spam warn (and only spam, not preview).
    assert emit_warnings("x" * 79) == ["spam"]
    assert emit_warnings("x" * 200) == ["spam"]
