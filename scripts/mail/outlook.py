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
                    cc: str | None = None,
                    to: str | None = None,
                    from_addr: str | None = None,
                    reply_to: str | None = None,
                    attachments=(),
                    ) -> None:
    """Create an Outlook mail draft with HTML body + optional headers."""
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = subject
    mail.HTMLBody = html
    if to:
        mail.To = to
    if cc:
        mail.CC = cc
    if bcc:
        mail.BCC = bcc
    if from_addr:
        # Shared mailbox / department address -- requires the user's
        # account to have Send-As permission for from_addr.
        mail.SentOnBehalfOfName = from_addr
    if reply_to:
        try:
            mail.ReplyRecipients.Add(reply_to)
        except Exception:
            log.debug("Outlook ReplyRecipients.Add(%r) failed", reply_to)
    for path in attachments or ():
        try:
            mail.Attachments.Add(str(path))
        except Exception:
            log.debug("Outlook Attachments.Add(%r) failed", path)
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
            draft.html, draft.subject,
            bcc=draft.bcc, cc=draft.cc, to=draft.to,
            from_addr=draft.from_addr, reply_to=draft.reply_to,
            attachments=draft.attachments,
        )


__all__ = ["compose_outlook", "is_available", "OutlookBackend"]
