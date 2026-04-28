"""Outlook desktop backend (Windows, via pywin32 COM).

Opens a brand-new mail item with HTMLBody (and optional BCC list)
already populated, then displays it -- the editor only types the To:
field and clicks Send.
"""

from __future__ import annotations

import logging
import platform

from scripts.mail.base import DraftEmail, MailHandler

log = logging.getLogger(__name__)


def is_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def compose_outlook(html: str, subject: str, *,
                    bcc: str | None = None,
                    to: str | None = None) -> None:
    """Create an Outlook mail draft with HTML body + optional BCC."""
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = subject
    mail.HTMLBody = html
    if to:
        mail.To = to
    if bcc:
        mail.BCC = bcc
    mail.Display(False)


class OutlookBackend:
    """MailBackend implementation for Outlook desktop on Windows."""

    name = "outlook"

    def is_available(self) -> bool:
        return is_available()

    def matches(self, handler: MailHandler) -> bool:
        return handler.is_outlook_desktop

    def compose(self, draft: DraftEmail) -> None:
        compose_outlook(
            draft.html, draft.subject, bcc=draft.bcc, to=draft.to,
        )


__all__ = ["compose_outlook", "is_available", "OutlookBackend"]
