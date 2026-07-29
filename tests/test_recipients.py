"""Tests for the recipients-list reader."""

from __future__ import annotations

from pathlib import Path

from scripts.recipients import load_recipients, sanitize_addresses


# ---------- sanitize_addresses -----------------------------------------
#
# `load_recipients` is a thin wrapper over this. It was extracted so that
# every path which can put an address into an outgoing draft shares one
# guard -- the browser build takes addresses from a textarea and had
# inherited none of these protections.

def test_sanitize_rejects_header_injection():
    """CR/LF in a header value makes `EmailMessage` raise, which reached
    the editor as an unexplained crash. It is also the classic
    header-injection vector, so it must never reach the draft."""
    accepted, rejected, _ = sanitize_addresses([
        "good@example.ac.jp",
        "evil@example.ac.jp\r\nBcc: attacker@evil.test",
        "evil2@example.ac.jp\nX-Injected: yes",
    ])
    assert accepted == ["good@example.ac.jp"]
    assert len(rejected) == 2


def test_sanitize_rejects_separator_smuggling():
    """One entry must never expand into several recipients."""
    accepted, rejected, _ = sanitize_addresses([
        "a@example.ac.jp, sneaky@evil.test",
        "b@example.ac.jp; sneaky2@evil.test",
    ])
    assert accepted == []
    assert len(rejected) == 2


def test_sanitize_rejects_display_name_form():
    """`Name <a@x>; Name2 <b@y>` would otherwise survive as one opaque
    string, and RFC 5322 would read the `;` as a group terminator --
    silently keeping only the first recipient."""
    accepted, rejected, _ = sanitize_addresses([
        "Katsuno <dean@example.ac.jp>",
        "<office@example.ac.jp>",
    ])
    assert accepted == []
    assert len(rejected) == 2


def test_sanitize_folds_fullwidth_at_sign():
    """NFKC runs before the pattern, so a Word-pasted fullwidth `＠`
    cannot slip past the `@`-based validation."""
    accepted, _, _ = sanitize_addresses(["victim＠example.ac.jp"])
    assert accepted == ["victim@example.ac.jp"]


def test_sanitize_deduplicates_and_preserves_order():
    accepted, rejected, _ = sanitize_addresses(
        ["b@example.ac.jp", "a@example.ac.jp", "b@example.ac.jp"])
    assert accepted == ["b@example.ac.jp", "a@example.ac.jp"]
    assert rejected == []


def test_sanitize_skips_blanks_and_comments_silently():
    """Comment lines are expected in a recipients.txt and must not be
    reported to the editor as rejected addresses."""
    accepted, rejected, _ = sanitize_addresses(
        ["# the department list", "", "   ", "a@example.ac.jp"])
    assert accepted == ["a@example.ac.jp"]
    assert rejected == []


def test_sanitize_reports_what_it_dropped():
    """The caller needs the rejects to tell the editor about them --
    silently dropping a recipient is worse than refusing the build."""
    _, rejected, _ = sanitize_addresses(["not an address", "also-bad@"])
    assert rejected == ["not an address", "also-bad@"]


def test_sanitize_reports_truncation_only_when_it_truncated():
    """The cap check used to run AFTER appending, so a list of exactly
    `_MAX_RECIPIENTS` valid addresses -- a complete list -- reported
    itself as truncated and sent the editor hunting for missing
    recipients that were never missing."""
    from scripts.recipients import _MAX_RECIPIENTS

    exact = [f"person{i:05d}@example.ac.jp" for i in range(_MAX_RECIPIENTS)]
    accepted, _, truncated = sanitize_addresses(exact)
    assert len(accepted) == _MAX_RECIPIENTS
    assert truncated is False, "a full-but-complete list is not truncated"

    accepted, _, truncated = sanitize_addresses(
        exact + ["one-too-many@example.ac.jp"])
    assert len(accepted) == _MAX_RECIPIENTS
    assert truncated is True
    assert "one-too-many@example.ac.jp" not in accepted


def test_load_recipients_warns_only_on_real_truncation(tmp_path: Path, caplog):
    from scripts.recipients import _MAX_RECIPIENTS

    exact = "\n".join(
        f"person{i:05d}@example.ac.jp" for i in range(_MAX_RECIPIENTS))
    path = tmp_path / "recipients.txt"

    path.write_text(exact, encoding="utf-8")
    caplog.clear()
    assert len(load_recipients(path)) == _MAX_RECIPIENTS
    assert "truncated" not in caplog.text

    path.write_text(exact + "\nover@example.ac.jp", encoding="utf-8")
    caplog.clear()
    assert len(load_recipients(path)) == _MAX_RECIPIENTS
    assert "truncated" in caplog.text



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


def test_load_recipients_normalises_fullwidth_at(tmp_path: Path):
    """Round-10 security MEDIUM: `_EMAIL_RE`'s exclusion class
    `[^@\\s;,<>]` only rejects ASCII `@` (U+0040); a crafted
    `victim<U+FF20>evil.com` (FULLWIDTH COMMERCIAL AT) would have passed
    validation AND routed to Outlook BCC, where COM might or might not
    auto-fold. Bundle 29 NFKC-normalises BEFORE regex matching, so
    fullwidth variants are always folded to ASCII first."""
    path = tmp_path / "recipients.txt"
    # Fullwidth `@` (U+FF20) and fullwidth `.` (U+FF0E) should fold to ASCII.
    path.write_text(
        "alice@example.com\n"
        "victim＠evil．com\n",  # both fullwidth
        encoding="utf-8",
    )
    out = load_recipients(path)
    # After NFKC normalisation the smuggled address is now structurally
    # equal to the visible-looking `victim@evil.com`. The point is that
    # the editor sees what Outlook will resolve -- no hidden routing.
    assert "alice@example.com" in out
    assert "victim@evil.com" in out
    # No entries with fullwidth chars survived to BCC.
    for addr in out:
        assert "＠" not in addr
        assert "．" not in addr


def test_load_recipients_normalises_fullwidth_digits(tmp_path: Path):
    """`１２３@example.com` -> `123@example.com` after NFKC."""
    path = tmp_path / "recipients.txt"
    path.write_text("user１２３@example.com\n", encoding="utf-8")
    out = load_recipients(path)
    assert out == ["user123@example.com"]


def test_load_recipients_rejects_zwj_smuggled_address(tmp_path: Path):
    """Round-9 security finding: U+200D ZERO WIDTH JOINER is not
    whitespace and not in `_EMAIL_RE`'s exclusion class, so a crafted
    `victim<ZWJ>@evil.com` would have passed recipient validation
    AND routed to Outlook BCC. Bundle 28 strips ZWJ in
    `strip_invisibles` by default; this test pins that fix."""
    path = tmp_path / "recipients.txt"
    # `victim` + ZWJ + `@evil.com` -- visually identical to the
    # legitimate `victim@evil.com`, but if ZWJ survives stripping the
    # local part the regex matches AND Outlook may resolve it
    # differently.
    path.write_text(
        "alice@example.com\n"
        "victim‍@evil.com\n",  # ZWJ between victim and @
        encoding="utf-8",
    )
    out = load_recipients(path)
    # After ZWJ-strip, the address normalises to `victim@evil.com`,
    # which is a structurally valid email -- so the entry IS accepted,
    # but as the visually-correct address (no hidden routing trick).
    # The point of the fix is that the pre/post-strip strings now
    # match -- there's no smuggling.
    assert out == ["alice@example.com", "victim@evil.com"]


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
