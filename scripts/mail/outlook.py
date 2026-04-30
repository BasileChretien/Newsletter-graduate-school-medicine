"""Outlook desktop backend (Windows, via pywin32 COM).

Opens a brand-new mail item with HTMLBody (and optional BCC list)
already populated, then displays it -- the editor only types the To:
field and clicks Send.
"""

from __future__ import annotations

import logging
import platform

from scripts.mail.base import DraftEmail, MailHandler
from scripts.mail.cid import InlineImage
from scripts.mail.plaintext import (
    html_to_plaintext, html_to_plaintext_strict_fallback,
)


# MAPI tag for the `Content-ID` header on an attachment, as documented
# at https://learn.microsoft.com/en-us/office/client-developer/outlook/mapi/pidtagattachcontentid-canonical-property.
# The 0x3712001F suffix encodes the property type (`PT_UNICODE`).
_PR_ATTACH_CONTENT_ID = (
    "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
)
# Hide CID-attached images from the "Attachments:" UI -- they are
# logically *inside* the message body, not separate attachments.
# 0x37140003 is `PR_ATTACH_FLAGS` (PT_LONG); the value 4 means
# `ATT_MHTML_REF` (the attachment is referenced by an HTML body).
_PR_ATTACH_FLAGS = (
    "http://schemas.microsoft.com/mapi/proptag/0x37140003"
)
_ATT_MHTML_REF = 4
# `PR_ATTACHMENT_HIDDEN` (PT_BOOLEAN) -- complementary to ATT_MHTML_REF
# on some Outlook builds; harmless when redundant.
_PR_ATTACHMENT_HIDDEN = (
    "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
)
# `PR_ATTACH_MIME_TAG` (PT_UNICODE) -- explicit MIME content-type for
# the attachment part. Some Outlook builds set this from the file
# extension automatically, but writing it explicitly is the surest
# way to force `Content-Type: image/jpeg` rather than the generic
# `application/octet-stream` default. Round-12 deliverability HIGH 1
# (Gmail web "shows as attachment" risk).
_PR_ATTACH_MIME_TAG = (
    "http://schemas.microsoft.com/mapi/proptag/0x370E001F"
)
# `PR_ATTACH_PATHNAME` (PT_UNICODE) -- the local-disk path the editor's
# PC uses. Some Exchange transport rules echo this into NDR debug
# headers. Clearing it explicitly avoids leaking editor-PC paths
# (round-12 deliverability MEDIUM 3).
_PR_ATTACH_PATHNAME = (
    "http://schemas.microsoft.com/mapi/proptag/0x3708001F"
)


def _ext_to_mime(path: str) -> str:
    """Map a file extension to the right MIME tag for `PR_ATTACH_MIME_TAG`.

    Conservative -- only the formats the toolkit's image_handler
    accepts. An unknown extension returns `application/octet-stream`
    so the attachment still ships, just without inline-disposition
    nudging.
    """
    lower = path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".bmp"):
        return "image/bmp"
    return "application/octet-stream"

log = logging.getLogger(__name__)


# COM-error tuple used by the narrow except clauses on `mail.*`
# property setters. Round-10 security LOW 4 + python-reviewer MEDIUM:
# `pywintypes.com_error` is `OSError`-derived in pywin32 >= 228 (2021)
# but inherits directly from `Exception` in older builds still common
# on locked-down university Windows images. So we import lazily and
# build a tuple that works in both environments. `AttributeError`
# stays in the tuple for the case where a renamed COM property turns
# the call into an attribute miss.
try:
    import pywintypes  # type: ignore[import-not-found]
    _COM_ERRORS: tuple[type[BaseException], ...] = (
        OSError, AttributeError, pywintypes.com_error,
    )
except ImportError:
    _COM_ERRORS = (OSError, AttributeError)


def is_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def _attach_inline_image(mail, inline: InlineImage) -> None:
    """Add `inline.path` to the Outlook draft as a CID-referenced part.

    Three MAPI property writes per attachment:

    * `PR_ATTACH_CONTENT_ID` -- sets the `Content-ID:` MIME header so
      the HTML's `<img src="cid:foo">` resolves to this attachment.
    * `PR_ATTACH_FLAGS = ATT_MHTML_REF` -- marks the attachment as
      "referenced by HTML", which on most Outlook builds keeps it out
      of the visible "Attachments:" row.
    * `PR_ATTACHMENT_HIDDEN = True` -- belt-and-braces equivalent on
      builds where MHTML_REF alone doesn't hide the row.

    All three calls go through the COM exception tuple so a build of
    pywin32 that exposes a different error class doesn't crash the
    compose path (the editor would still get the email; just with
    the inline images visible as named attachments).
    """
    try:
        att = mail.Attachments.Add(str(inline.path))
    except _COM_ERRORS as e:
        log.warning(
            "Outlook Attachments.Add(%s) failed for inline image (%s); "
            "the email will reference cid:%s but no attachment will "
            "carry it -- recipients will see a broken image.",
            inline.path, e, inline.cid,
        )
        return
    try:
        att.PropertyAccessor.SetProperty(
            _PR_ATTACH_CONTENT_ID, inline.cid,
        )
    except _COM_ERRORS as e:
        log.warning(
            "Outlook PropertyAccessor.SetProperty(Content-ID=%r) "
            "failed (%s); inline image will appear as a normal "
            "attachment instead of an inline reference.",
            inline.cid, e,
        )
        return
    # Hide-from-attachments UI bits are best-effort. If they fail we
    # still have a working CID-referenced image; the recipient just
    # also sees it in the attachments row, which is cosmetic.
    try:
        att.PropertyAccessor.SetProperty(
            _PR_ATTACH_FLAGS, _ATT_MHTML_REF,
        )
    except _COM_ERRORS as e:
        log.debug("PR_ATTACH_FLAGS set failed (%s); cosmetic only.", e)
    try:
        att.PropertyAccessor.SetProperty(
            _PR_ATTACHMENT_HIDDEN, True,
        )
    except _COM_ERRORS as e:
        log.debug("PR_ATTACHMENT_HIDDEN set failed (%s); cosmetic only.", e)
    # Round-12 deliverability HIGH 1: explicitly write the MIME type
    # so Gmail web doesn't fall back to "show as attachment" when
    # Outlook's auto-detection produces `application/octet-stream`
    # on certain Click-to-Run builds.
    try:
        att.PropertyAccessor.SetProperty(
            _PR_ATTACH_MIME_TAG, _ext_to_mime(str(inline.path)),
        )
    except _COM_ERRORS as e:
        log.debug("PR_ATTACH_MIME_TAG set failed (%s); cosmetic only.", e)
    # Round-12 deliverability MEDIUM 3: explicitly clear the on-disk
    # pathname so transport-rule debug headers can't leak the
    # editor's local file system layout.
    try:
        att.PropertyAccessor.SetProperty(_PR_ATTACH_PATHNAME, "")
    except _COM_ERRORS as e:
        log.debug("PR_ATTACH_PATHNAME clear failed (%s); cosmetic only.", e)


def compose_outlook(html: str, subject: str, *,
                    bcc: str | None = None,
                    cc: str | None = None,
                    to: str | None = None,
                    from_addr: str | None = None,
                    reply_to: str | None = None,
                    attachments=(),
                    inline_images: tuple[InlineImage, ...] = (),
                    ) -> None:
    """Create an Outlook mail draft with HTML body + optional headers.

    We set BOTH `HTMLBody` and `Body` so Outlook serializes a
    `multipart/alternative` MIME message: HTML for clients that
    render it, plaintext for clients that don't (and as a hint to
    spam filters that this isn't HTML-only mail). Mimecast /
    Proofpoint / MS Defender all score HTML-only mail higher.

    When `inline_images` is non-empty, the `html` is expected to
    already contain `<img src="cid:...">` references (the rewriting
    happens in `scripts.mail.cid.attach_inline_images` before the
    backend is called). We attach each `InlineImage`'s file via the
    COM Attachments.Add() API and tag it with the matching
    `Content-ID:` header so the HTML references resolve.
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
        # COM call may raise `pywintypes.com_error` (which is
        # `OSError`-derived only on pywin32 >= 228) for unresolvable
        # addresses. The `_COM_ERRORS` tuple at module load builds a
        # version-aware union so older pywin32 doesn't slip past the
        # narrow except.
        try:
            mail.ReplyRecipients.Add(reply_to)
        except _COM_ERRORS as e:
            log.debug("Outlook ReplyRecipients.Add(%r) failed: %s",
                      reply_to, e)
    for path in attachments or ():
        try:
            mail.Attachments.Add(str(path))
        except _COM_ERRORS as e:
            log.debug("Outlook Attachments.Add(%r) failed: %s", path, e)
    # Inline images (CID mode): attach each file AND tag it with the
    # matching Content-ID header so the HTML's `<img src="cid:...">`
    # references resolve. Order doesn't matter; Outlook deduplicates
    # by path internally. The signature default is `()`, so iterating
    # is a no-op when CID mode is off -- no `or ()` guard needed.
    for inline in inline_images:
        _attach_inline_image(mail, inline)
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
            inline_images=draft.inline_images,
        )


__all__ = ["compose_outlook", "is_available", "OutlookBackend"]
