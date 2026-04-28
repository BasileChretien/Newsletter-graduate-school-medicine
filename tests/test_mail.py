"""Tests for the composer (mail-handler detection + backend dispatch)."""

from __future__ import annotations

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
    assert isinstance(used, ComposeOutcome)
    assert used.backend == "outlook"
    assert not used.is_fallback
    # Legacy str() format is preserved.
    assert str(used) == "outlook"
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
    assert str(used) == "default:apple_mail"
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
    # Legacy fallback magic-string format preserved for any older
    # call site or log-grep.
    assert str(used) == "default:outlook:fallback-from-outlook"
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


# ---------- Bundle 27: ComposeOutcome shape ------------------------------

def test_compose_outcome_is_frozen_dataclass():
    """`ComposeOutcome` must be immutable so callers can't mutate
    the result and confuse downstream logging / audit."""
    out = ComposeOutcome(backend="outlook", handler_kind="outlook")
    with pytest.raises(Exception):  # FrozenInstanceError
        out.backend = "other"  # type: ignore[misc]


def test_compose_outcome_str_legacy_formats():
    """The `__str__` shim must reproduce every legacy magic string
    the round-7 stringly-typed return produced, so log-grep keeps
    working during the migration."""
    assert str(ComposeOutcome(
        backend="outlook", handler_kind="outlook",
    )) == "outlook"
    assert str(ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    )) == "default:apple_mail"
    assert str(ComposeOutcome(
        backend="clipboard_mailto", handler_kind="browser",
    )) == "default:browser"
    assert str(ComposeOutcome(
        backend="clipboard_mailto", handler_kind="outlook",
        fell_back_from="outlook",
    )) == "default:outlook:fallback-from-outlook"


def test_compose_outcome_startswith_compatibility():
    """Legacy code may still call `outcome.startswith("default:")` --
    keep the shim so existing log-grep / debug paths don't break."""
    assert ComposeOutcome(
        backend="clipboard_mailto", handler_kind="apple_mail",
    ).startswith("default:")
    assert not ComposeOutcome(
        backend="outlook", handler_kind="outlook",
    ).startswith("default:")
