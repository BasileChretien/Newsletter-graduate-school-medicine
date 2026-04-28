"""Top-level mail-backend dispatch.

Public API:
    detect_default_mail_handler() -> MailHandler
    load_recipients(path) -> list[str]
    compose(html, *, subject, backend="auto", preview_path=None,
            bcc=None, to=None) -> str
"""

from __future__ import annotations

import logging
import urllib.parse
import webbrowser
from pathlib import Path

from scripts.mail.base import MailHandler
from scripts.mail.clipboard import copy_html_to_clipboard
from scripts.mail.detect import detect_default_mail_handler
from scripts.mail.outlook import compose_outlook, is_available as _outlook_com_available

log = logging.getLogger(__name__)


def load_recipients(recipients_path: Path) -> list[str]:
    """Read a `recipients.txt` -- one address per line, # comments allowed.

    Returns the list of email addresses. Missing or empty file -> [].
    """
    if not recipients_path.exists():
        return []
    out: list[str] = []
    for raw in recipients_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line.rstrip(",").strip())
    return out


def compose_via_default(html: str, subject: str, *,
                        preview_path: Path | None = None,
                        handler: MailHandler | None = None) -> None:
    """Copy HTML to clipboard and launch the OS default mail handler."""
    copied = copy_html_to_clipboard(html)
    mailto = "mailto:?subject=" + urllib.parse.quote(subject)
    webbrowser.open(mailto)
    if preview_path is not None and preview_path.exists():
        webbrowser.open(preview_path.as_uri())
    handler_label = f"({handler.name})" if handler else ""
    if copied:
        log.info("HTML copied to clipboard %s -- paste with Ctrl+V into the email body.",
                 handler_label)
    else:
        log.warning(
            "Could not copy HTML to clipboard automatically %s. "
            "Copy from the preview window: Ctrl+A then Ctrl+C.",
            handler_label,
        )


def compose(html: str, *, subject: str, backend: str = "auto",
            preview_path: Path | None = None,
            bcc: str | None = None,
            to: str | None = None) -> str:
    """Open an email draft. Returns the backend used."""
    if backend not in ("auto", "outlook", "default"):
        raise ValueError(
            f"backend must be 'auto', 'outlook' or 'default' -- got {backend!r}")

    handler = detect_default_mail_handler()
    log.info("Default mail handler: %s [%s]", handler.name, handler.kind)

    use_outlook = (
        backend == "outlook"
        or (backend == "auto" and handler.is_outlook_desktop
            and _outlook_com_available())
    )
    if use_outlook:
        try:
            compose_outlook(html, subject, bcc=bcc, to=to)
            return "outlook"
        except Exception as e:
            log.warning("Outlook draft failed (%s) -- falling back to default handler.", e)
            if backend == "outlook":
                raise

    compose_via_default(html, subject, preview_path=preview_path,
                        handler=handler)
    return f"default:{handler.kind}"


__all__ = [
    "MailHandler",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
    "detect_default_mail_handler",
    "load_recipients",
]
