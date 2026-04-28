"""Tests for the recipients-list reader."""

from __future__ import annotations

from pathlib import Path

from scripts.recipients import load_recipients


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


def test_load_recipients_rejects_separator_injection(tmp_path: Path):
    """A line that smuggles `; bcc=evil@x.com` must be rejected, not
    expanded into multiple Outlook BCC entries."""
    path = tmp_path / "recipients.txt"
    path.write_text(
        "alice@example.com\n"
        "attacker@evil.com; bcc=second@evil.com\n"
        "comma,injection@evil.com\n",
        encoding="utf-8",
    )
    out = load_recipients(path)
    assert out == ["alice@example.com"]


def test_load_recipients_rejects_obvious_typos(tmp_path: Path):
    path = tmp_path / "recipients.txt"
    path.write_text(
        "good@example.com\n"
        "no-at-sign\n"
        "missing@tld\n"
        "spaces in@example.com\n",
        encoding="utf-8",
    )
    out = load_recipients(path)
    assert out == ["good@example.com"]


def test_load_recipients_deduplicates(tmp_path: Path):
    path = tmp_path / "recipients.txt"
    path.write_text(
        "alice@example.com\n"
        "alice@example.com\n"
        "bob@example.org\n",
        encoding="utf-8",
    )
    out = load_recipients(path)
    assert out == ["alice@example.com", "bob@example.org"]


def test_load_recipients_strips_unicode_invisibles(tmp_path: Path):
    """Zero-width / bidi-override characters hidden inside an address
    must be stripped before validation -- otherwise the address that
    looks correct in the editor's text file resolves to a different
    recipient inside Outlook."""
    path = tmp_path / "recipients.txt"
    # ZWSP (​) hidden between 'a' and 'lice'
    path.write_text(
        "a​lice@example.com\n"
        "bob‮@example.org\n"  # RLO between bob and @
        "﻿carol@example.net\n",  # BOM at start
        encoding="utf-8",
    )
    out = load_recipients(path)
    assert out == [
        "alice@example.com",
        "bob@example.org",
        "carol@example.net",
    ]
