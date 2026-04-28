"""Outlook desktop backend (Windows, via pywin32 COM).

Opens a brand-new mail item with HTMLBody (and optional BCC list)
already populated, then displays it -- the editor only types the To:
field and clicks Send.
"""

from __future__ import annotations

import logging
import platform

from scripts.mail.base import DraftEmail, MailHandler
from scripts.mail.plaintext import (
    html_to_plaintext, html_to_plaintext_strict_fallback,
)

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
    """Create an Outlook mail draft with HTML body + optional headers.

    We set BOTH `HTMLBody` and `Body` so Outlook serializes a
    `multipart/alternative` MIME message: HTML for clients that
    render it, plaintext for clients that don't (and as a hint to
    spam filters that this isn't HTML-only mail). Mimecast /
    Proofpoint / MS Defender all score HTML-only mail higher.
    """
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)  # 0 = olMailItem
    mail.Subject = subject
    # Plaintext FIRST, then HTMLBody -- Outlook's Body is replaced
    # by an auto-generated text version when you set HTMLBody, so
    # if we want a real plaintext alternative we set HTMLBody first
    # then overwrite Body with our cleaner conversion.
    mail.HTMLBody = html
    # Plaintext alternative -- spam filters score multipart/alternative
    # lower than HTML-only. Always set Body to SOMETHING (never let
    # Outlook auto-generate from HTML, which it does poorly): primary
    # path is `html_to_plaintext` (structurally preserved); on
    # exception, fall back to a strict regex strip so the MIME message
    # still ships as `multipart/alternative`.
    try:
        mail.Body = html_to_plaintext(html)
    except Exception as e:  # noqa: BLE001 -- plaintext is best-effort
        log.warning(
            "html_to_plaintext failed (%s); falling back to strict "
            "tag-strip plaintext to keep multipart/alternative.", e,
        )
        try:
            mail.Body = html_to_plaintext_strict_fallback(html)
        except Exception as e2:  # noqa: BLE001 -- last resort
            log.warning(
                "Strict plaintext fallback also failed (%s); Outlook "
                "will auto-generate Body from HTML (lower-quality).",
                e2,
            )
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
        # COM call may raise pywintypes.com_error (which is OSError-
        # derived in modern pywin32) for unresolvable addresses.
        # Narrow except so a real bug (AttributeError on a renamed
        # COM property) isn't silently swallowed.
        try:
            mail.ReplyRecipients.Add(reply_to)
        except (OSError, AttributeError) as e:
            log.debug("Outlook ReplyRecipients.Add(%r) failed: %s",
                      reply_to, e)
    for path in attachments or ():
        try:
            mail.Attachments.Add(str(path))
        except (OSError, AttributeError) as e:
            log.debug("Outlook Attachments.Add(%r) failed: %s", path, e)
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
