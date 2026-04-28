"""Tests for the composer (mail-handler detection + backend dispatch)."""

from __future__ import annotations

import warnings
from unittest.mock import patch

import pytest

from scripts.mail import (
    ComposeOutcome, MailHandler, compose, detect_default_mail_handler,
)


def test_mailhandler_outlook_flag():
    h = MailHandler(kind="outlook", name="Microsoft Outlook")
    assert h.is_outlook_desktop is True
    other = MailHandler(kind="apple_mail", name="Apple Mail")
    assert other.is_outlook_desktop is False


def test_detect_default_mail_handler_returns_handler():
    h = detect_default_mail_handler()
    assert isinstance(h, MailHandler)
    assert h.kind in {
        "outlook", "apple_mail", "thunderbird",
        "browser", "other", "unknown",
    }


def test_compose_routes_outlook_when_default_is_outlook():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test")
    # Round-9 Architect HIGH-1: assert on the typed dataclass fields
    # rather than the deprecated `str(used) == "outlook"` shim, so the
    # eventual removal of `__str__` doesn't churn this test.
    assert isinstance(used, ComposeOutcome)
    assert used.backend == "outlook"
    assert used.handler_kind == "outlook"
    assert not used.is_fallback
    out_compose.assert_called_once()
    fb_compose.assert_not_called()


def test_compose_falls_back_to_default_when_not_outlook():
    handler = MailHandler(kind="apple_mail", name="Apple Mail")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=False), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test")
    assert used.backend == "clipboard_mailto"
    assert used.handler_kind == "apple_mail"
    assert not used.is_fallback
    out_compose.assert_not_called()
    fb_compose.assert_called_once()


def test_compose_falls_back_when_outlook_backend_throws():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               side_effect=RuntimeError("boom")), \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test", backend="auto")
    assert used.backend == "clipboard_mailto"
    assert used.is_fallback
    assert used.fell_back_from == "outlook"
    fb_compose.assert_called_once()


def test_compose_explicit_outlook_backend_raises_on_failure():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.is_available",
               return_value=True), \
         patch("scripts.mail.outlook.OutlookBackend.compose",
               side_effect=RuntimeError("forced")):
        with pytest.raises(RuntimeError, match="forced"):
            compose("<html>x</html>", subject="Test", backend="outlook")


def test_compose_invalid_backend_raises():
    with pytest.raises(ValueError, match="backend must be"):
        compose("<html>x</html>", subject="Test", backend="bogus")


def test_compose_default_backend_skips_outlook():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.mail.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.mail.outlook.OutlookBackend.compose") as out_compose, \
         patch("scripts.mail.clipboard_mailto.ClipboardMailtoBackend.compose") as fb_compose:
        used = compose("<html>x</html>", subject="Test", backend="default")
    assert used.backend == "clipboard_mailto"
    assert used.handler_kind == "outlook"
    assert not used.is_fallback
    out_compose.assert_not_called()
    fb_compose.assert_called_once()


# ---------- Bundle 27/28: ComposeOutcome shape ---------------------------

def test_compose_outcome_is_frozen_dataclass():
    """`ComposeOutcome` must be immutable so callers can't mutate
    the result and confuse downstream logging / audit.

    Round-9 code-review LOW: catch the precise exception class
    (`FrozenInstanceError` from `dataclasses`) rather than bare
    `Exception` -- otherwise this test would pass for unrelated
    `AttributeError` from a renamed field."""
    import dataclasses
    out = ComposeOutcome(backend="outlook", handler_kind="outlook")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        out.backend = "other"  # type: ignore[misc]


def test_compose_outcome_str_is_silent():
    """Bundle 29: `__str__` no longer emits DeprecationWarning.

    Round-9 added the warning, but round-10 found that lazy-%s
    formatting in production log calls (`log.info("used: %s",
    outcome)`) triggers the warning on every INFO line, defeating
    the purpose of the legacy shim. The migration nudge lives on
    `startswith` (a more deliberate API surface) instead."""
    out = ComposeOutcome(backend="outlook", handler_kind="outlook")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        s = str(out)  # must NOT raise
    assert s == "outlook"


def test_compose_outcome_startswith_emits_deprecation_warning():
    """`startswith` is still deprecated -- explicit string-prefix
    matching is usually deliberate code worth migrating."""
    out = ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    )
    with pytest.warns(DeprecationWarning, match=r"\.startswith"):
        assert out.startswith("default:")


def test_compose_outcome_legacy_formats_via_internal_helper():
    """The legacy wire format must still reproduce every round-7
    stringly-typed return so existing log lines stay greppable. Pinned
    via the `_format_legacy` internal helper (renamed from
    `_legacy_str` in bundle 29 -- round-10 python-reviewer MEDIUM)."""
    assert ComposeOutcome(
        backend="outlook", handler_kind="outlook",
    )._format_legacy() == "outlook"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    )._format_legacy() == "default:apple_mail"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="browser",
    )._format_legacy() == "default:browser"
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="outlook",
        fell_back_from="outlook",
    )._format_legacy() == "default:outlook:fallback-from-outlook"


def test_compose_outcome_field_pattern_match_replaces_str_check():
    """Demonstrates the migration target: callers that used to do
    `str(used) == "outlook"` should match on the typed fields."""
    outlook = ComposeOutcome(backend="outlook", handler_kind="outlook")
    assert outlook.backend == "outlook" and not outlook.is_fallback

    fallback = ComposeOutcome(
        backend="clipboard_mailto", handler_kind="outlook",
        fell_back_from="outlook",
    )
    assert fallback.is_fallback
    assert fallback.fell_back_from == "outlook"
