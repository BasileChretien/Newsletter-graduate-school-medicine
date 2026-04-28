"""Tests for the shared text-sanitization primitives."""

from __future__ import annotations

from scripts.text_utils import (
    normalize_compatibility,
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
