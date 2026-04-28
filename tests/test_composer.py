"""Tests for the composer (mail-handler detection + dispatch)."""

from __future__ import annotations

from unittest.mock import patch

from scripts.composer import (
    MailHandler, compose, detect_default_mail_handler,
)


def test_mailhandler_outlook_flag():
    h = MailHandler(kind="outlook", name="Microsoft Outlook")
    assert h.is_outlook_desktop is True
    other = MailHandler(kind="apple_mail", name="Apple Mail")
    assert other.is_outlook_desktop is False


def test_detect_default_mail_handler_returns_handler():
    h = detect_default_mail_handler()
    assert isinstance(h, MailHandler)
    # Returns *something* — kind in known set.
    assert h.kind in {
        "outlook", "apple_mail", "thunderbird",
        "browser", "other", "unknown",
    }


def test_compose_routes_outlook_when_default_is_outlook():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.composer.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.composer._outlook_com_available", return_value=True), \
         patch("scripts.composer.compose_outlook") as mock_outlook, \
         patch("scripts.composer.compose_via_default") as mock_default:
        used = compose("<html>x</html>", subject="Test")
    assert used == "outlook"
    mock_outlook.assert_called_once()
    mock_default.assert_not_called()


def test_compose_falls_back_to_default_when_not_outlook():
    handler = MailHandler(kind="apple_mail", name="Apple Mail")
    with patch("scripts.composer.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.composer._outlook_com_available", return_value=False), \
         patch("scripts.composer.compose_outlook") as mock_outlook, \
         patch("scripts.composer.compose_via_default") as mock_default:
        used = compose("<html>x</html>", subject="Test")
    assert used.startswith("default:")
    mock_outlook.assert_not_called()
    mock_default.assert_called_once()


def test_compose_falls_back_when_outlook_com_throws():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.composer.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.composer._outlook_com_available", return_value=True), \
         patch("scripts.composer.compose_outlook",
               side_effect=RuntimeError("boom")), \
         patch("scripts.composer.compose_via_default") as mock_default:
        used = compose("<html>x</html>", subject="Test", backend="auto")
    assert used.startswith("default:")
    mock_default.assert_called_once()


def test_compose_explicit_outlook_backend_raises_on_failure():
    import pytest
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.composer.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.composer._outlook_com_available", return_value=True), \
         patch("scripts.composer.compose_outlook",
               side_effect=RuntimeError("forced")):
        with pytest.raises(RuntimeError, match="forced"):
            compose("<html>x</html>", subject="Test", backend="outlook")


def test_compose_invalid_backend_raises():
    import pytest
    with pytest.raises(ValueError, match="backend must be"):
        compose("<html>x</html>", subject="Test", backend="bogus")


def test_compose_default_backend_skips_outlook():
    handler = MailHandler(kind="outlook", name="Microsoft Outlook")
    with patch("scripts.composer.detect_default_mail_handler",
               return_value=handler), \
         patch("scripts.composer.compose_outlook") as mock_outlook, \
         patch("scripts.composer.compose_via_default") as mock_default:
        used = compose("<html>x</html>", subject="Test", backend="default")
    assert used.startswith("default:")
    mock_outlook.assert_not_called()
    mock_default.assert_called_once()
