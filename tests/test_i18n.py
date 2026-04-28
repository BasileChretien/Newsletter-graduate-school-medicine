"""Tests for the locale loader."""

from __future__ import annotations

from scripts.i18n import load_locale, t


def test_load_locale_en_has_keys():
    data = load_locale("en")
    assert "errors" in data
    assert "no_python" in data["errors"]
    assert isinstance(data["errors"]["no_python"], str)


def test_load_locale_ja_overrides_en():
    en = load_locale("en")
    ja = load_locale("ja")
    # Same key in both; values differ.
    assert en["errors"]["no_python"] != ja["errors"]["no_python"]
    # ja should contain Japanese characters somewhere.
    assert any(ord(c) > 0x3040 for c in ja["errors"]["no_python"])


def test_t_falls_back_to_english_on_missing_key():
    # Use a key that exists in en.toml.
    val_en = t("errors.no_python", locale="en")
    assert val_en
    # Unknown key returns default (or the key name).
    assert t("does.not.exist", default="X") == "X"
    assert t("does.not.exist") == "does.not.exist"


def test_unknown_locale_falls_back_to_english():
    en = load_locale("en")
    fr = load_locale("fr")  # not supported
    assert fr == en
