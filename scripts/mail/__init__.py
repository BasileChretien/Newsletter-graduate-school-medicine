"""Top-level mail-backend dispatch.

Backends are registered in priority order. `compose()` walks them and
picks the first one whose `matches()` accepts the detected handler AND
which `is_available()` returns True. To add a new backend (Thunderbird
XPCOM, Gmail OAuth, SMTP, ...), drop a module into `scripts/mail/`,
expose a class implementing the `MailBackend` Protocol, and append it
to `_BACKENDS` -- the dispatcher needs no edits.

Public API:
    detect_default_mail_handler() -> MailHandler
    load_recipients(path) -> list[str]
    compose(html, *, subject, backend="auto", preview_path=None,
            bcc=None, to=None) -> str
"""

from __future__ import annotations

import logging
from pathlib import Path

from scripts.mail.base import DraftEmail, MailBackend, MailHandler
from scripts.mail.clipboard import copy_html_to_clipboard
from scripts.mail.clipboard_mailto import (
    ClipboardMailtoBackend, compose_via_default,
)
from scripts.mail.detect import detect_default_mail_handler
from scripts.mail.outlook import OutlookBackend, compose_outlook, is_available
from scripts.recipients import load_recipients

log = logging.getLogger(__name__)


# Registry: ordered, priority high-to-low. The dispatcher iterates and
# stops at the first backend whose `matches(handler)` returns True AND
# whose `is_available()` returns True.
_BACKENDS: list[MailBackend] = [
    OutlookBackend(),         # Windows + Outlook desktop -- rich HTML draft
    ClipboardMailtoBackend(), # universal fallback
]


def _select_backend(name: str, handler: MailHandler) -> MailBackend:
    """Pick a backend by explicit name or auto-detect."""
    if name == "auto":
        for backend in _BACKENDS:
            if backend.matches(handler) and backend.is_available():
                return backend
        # Universal fallback always matches; ClipboardMailtoBackend wins.
        return _BACKENDS[-1]
    if name == "outlook":
        return next(b for b in _BACKENDS if b.name == "outlook")
    if name == "default":
        return next(b for b in _BACKENDS if b.name == "clipboard_mailto")
    raise ValueError(
        f"backend must be 'auto', 'outlook' or 'default' -- got {name!r}")


def compose(html: str, *, subject: str, backend: str = "auto",
            preview_path: Path | None = None,
            bcc: str | None = None,
            to: str | None = None) -> str:
    """Open an email draft. Returns the backend used.

    Failure modes:
      - `backend="outlook"` explicit + Outlook throws  -> re-raise.
        Caller MUST surface this to the editor so they don't think the
        BCC list silently went out via clipboard.
      - `backend="auto"` + Outlook throws -> warn loudly (so the editor
        notices the change), then fall back to the clipboard backend.
    """
    handler = detect_default_mail_handler()
    log.info("Default mail handler: %s [%s]", handler.name, handler.kind)

    chosen = _select_backend(backend, handler)
    draft = DraftEmail(
        html=html, subject=subject, bcc=bcc, to=to,
        preview_path=preview_path,
    )

    try:
        if chosen.name == "clipboard_mailto":
            # Universal fallback wants the handler for the log line.
            chosen.compose(draft, handler=handler)
        else:
            chosen.compose(draft)
    except Exception as e:
        if backend != "auto":
            # Explicit backend failed -- propagate so the caller can
            # abort with a non-zero exit and avoid silently dropping BCC.
            log.error("%s backend failed: %s", chosen.name, e)
            raise
        # Auto-fallback: make the change of plan VISIBLE to the editor.
        log.warning(
            "Outlook draft failed (%s). Falling back to clipboard + "
            "default mail handler. The newsletter is on your clipboard; "
            "paste with Ctrl+V into the message body.", e,
        )
        fallback = _BACKENDS[-1]
        fallback.compose(draft, handler=handler)
        return f"default:{handler.kind}:fallback-from-{chosen.name}"

    if chosen.name == "outlook":
        return "outlook"
    return f"default:{handler.kind}"


__all__ = [
    "DraftEmail",
    "MailBackend",
    "MailHandler",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
    "detect_default_mail_handler",
    "is_available",
    "load_recipients",
]
