"""Tests for the shared text-sanitization primitives."""

from __future__ import annotations

from scripts.text_utils import (
    normalize_compatibility,
    normalize_for_match,
    sanitize_subject,
    strip_invisibles,
)


def test_strip_invisibles_drops_zwsp_and_bom():
    assert strip_invisibles("a​lice") == "alice"
    assert strip_invisibles("﻿hello") == "hello"
    assert strip_invisibles("bo‮b") == "bob"  # RLO


def test_strip_invisibles_keeps_newlines_and_tabs():
    """Body-text callers depend on \\n / \\t survival."""
    assert strip_invisibles("a\nb\tc") == "a\nb\tc"


def test_normalize_compatibility_folds_nbsp_and_fullwidth():
    # NBSP -> ASCII space
    assert normalize_compatibility("VOL. XX") == "VOL. XX"
    # Fullwidth digits -> ASCII
    assert normalize_compatibility("１２３") == "123"


def test_sanitize_subject_strips_invisibles_and_collapses_whitespace():
    raw = "MERIDIAN ​  VOL.  12 ‮ | ISSUE 3"
    out = sanitize_subject(raw)
    # No leading/trailing whitespace, single spaces only, no invisibles
    assert out == "MERIDIAN VOL. 12 | ISSUE 3"


def test_sanitize_subject_empty():
    assert sanitize_subject("") == ""
    assert sanitize_subject("   ​   ") == ""


def test_sanitize_subject_leaves_normal_text_alone():
    assert sanitize_subject("MERIDIAN — VOL. 12 | ISSUE NO. 3 | MARCH 2026") \
        == "MERIDIAN — VOL. 12 | ISSUE NO. 3 | MARCH 2026"


# ---------- Bundle 26: ZWJ preservation (compound emoji) -----------------

def test_strip_invisibles_preserves_zwj_in_compound_emoji():
    """U+200D ZWJ joins emoji into single-glyph sequences (family,
    profession). Removing it shatters the glyph into separate emoji,
    so it must survive `strip_invisibles`."""
    # Family emoji: man + ZWJ + woman + ZWJ + girl
    family = "👨‍👩‍👧"
    assert strip_invisibles(family) == family


def test_strip_invisibles_preserves_zwj_in_text():
    """ZWJ also appears in Indic / Arabic scripts as a script joiner."""
    text = "a‍b"
    assert strip_invisibles(text) == "a‍b"


# ---------- Bundle 26: \r stripped (no longer in keep set) ---------------

def test_strip_invisibles_removes_carriage_return():
    """\\r is a control character and is now removed -- a stray CR
    in a subject line is a paste artefact, not a structural newline."""
    assert strip_invisibles("hello\rworld") == "helloworld"


def test_strip_invisibles_keeps_newlines_and_tabs_only():
    """Among C0/C1 controls, only \\n and \\t are still preserved."""
    assert strip_invisibles("a\nb\tc\rd") == "a\nb\tcd"


# ---------- Bundle 26: normalize_for_match -------------------------------

def test_normalize_for_match_folds_nbsp():
    """`VOL. XX` (NBSP between tokens) must normalize to ASCII so
    a plain substring `"VOL. XX"` check matches."""
    s = "VOL. XX | ISSUE NO. XX"
    assert "VOL. XX" in normalize_for_match(s)


def test_normalize_for_match_collapses_double_spaces():
    """Word's auto-format sometimes inserts double spaces after
    period; the masthead guard must still match."""
    assert "VOL. XX" in normalize_for_match("VOL.  XX | ISSUE NO. XX")


def test_normalize_for_match_does_not_strip_leading_or_trailing():
    """`normalize_for_match` is for substring matching, NOT for
    presentation. It must NOT strip leading/trailing whitespace --
    a caller that relies on .startswith(' ') would otherwise fail."""
    s = "  hello  "
    out = normalize_for_match(s)
    # Whitespace runs collapse to single space, but ends are preserved.
    assert out == " hello "


def test_normalize_for_match_folds_fullwidth_digits():
    """NFKC folds fullwidth digits to ASCII, so a Japanese editor
    typing １２ in the issue line gets it normalized."""
    assert normalize_for_match("VOL. １２") == "VOL. 12"
