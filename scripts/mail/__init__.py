"""Top-level mail-backend dispatch.

Public API:
    detect_default_mail_handler() -> MailHandler
    load_recipients(path) -> list[str]
    compose(html, *, subject, backend="auto", preview_path=None,
            bcc=None, to=None) -> str
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import webbrowser
from pathlib import Path

from scripts.mail.base import MailHandler
from scripts.mail.clipboard import copy_html_to_clipboard
from scripts.mail.detect import detect_default_mail_handler
from scripts.mail.outlook import compose_outlook, is_available as _outlook_com_available

log = logging.getLogger(__name__)


# Loose RFC 5322 -- enough to reject obvious typos plus header/separator
# injection (`;`, `,`, CR/LF) without overfitting on valid edge cases.
_EMAIL_RE = re.compile(r"^[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+$")
# Hard ceiling -- a runaway recipients.txt cannot generate a 50 MB BCC.
_MAX_RECIPIENTS = 1000


def load_recipients(recipients_path: Path) -> list[str]:
    """Read a `recipients.txt` -- one address per line, # comments allowed.

    Each non-comment line is validated against a loose RFC 5322 pattern and
    rejected if it contains a separator character (`;`, `,`, CR/LF) that
    Outlook's BCC parser would split on -- prevents a malicious or typo'd
    line from expanding into multiple recipients. Result is deduplicated
    and capped at _MAX_RECIPIENTS entries.
    """
    if not recipients_path.exists():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in recipients_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().rstrip(",").strip()
        if not line or line.startswith("#"):
            continue
        if not _EMAIL_RE.match(line):
            log.warning(
                "Skipping invalid recipient (not a valid e-mail address "
                "or contains a separator character): %r", line)
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= _MAX_RECIPIENTS:
            log.warning(
                "recipients.txt has more than %d entries -- truncated.",
                _MAX_RECIPIENTS)
            break
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
