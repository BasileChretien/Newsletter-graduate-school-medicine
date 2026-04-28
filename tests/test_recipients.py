"""Tests for the recipients-list reader."""

from __future__ import annotations

from pathlib import Path

from scripts.composer import load_recipients


def test_load_recipients_empty_when_missing(tmp_path: Path):
    assert load_recipients(tmp_path / "missing.txt") == []


def test_load_recipients_strips_comments_and_blank_lines(tmp_path: Path):
    path = tmp_path / "recipients.txt"
    path.write_text(
        "# comment\n"
        "alice@example.com\n"
        "\n"
        "  # indented comment\n"
        "bob@example.org\n"
        "carol@example.net,\n",
        encoding="utf-8",
    )
    out = load_recipients(path)
    assert out == ["alice@example.com", "bob@example.org", "carol@example.net"]
