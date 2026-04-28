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
            bcc=None, to=None) -> ComposeOutcome
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

from scripts.mail.base import DraftEmail, MailBackend, MailHandler
from scripts.mail.clipboard import copy_html_to_clipboard
from scripts.mail.clipboard_mailto import (
    ClipboardMailtoBackend, compose_via_default,
)
from scripts.mail.detect import detect_default_mail_handler
from scripts.mail.outlook import OutlookBackend, compose_outlook
from scripts.recipients import load_recipients

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComposeOutcome:
    """Typed result of a `compose()` call.

    Replaces the round-7 stringly-typed return (`"outlook"`,
    `"default:apple_mail"`, `"default:browser:fallback-from-outlook"`)
    with three explicit fields:

    * `backend`         -- name of the backend that actually composed
                           the draft (`"outlook"`, `"clipboard_mailto"`).
    * `handler_kind`    -- detected default-mail-handler kind
                           (`"outlook"`, `"apple_mail"`, `"thunderbird"`,
                           `"browser"`, `"other"`, `"unknown"`).
    * `fell_back_from`  -- if the auto-path attempted Outlook and it
                           threw, this holds `"outlook"`. None otherwise.

    `__str__` preserves the legacy magic-string wire format so
    existing log lines and any string-comparing call sites keep
    working during the migration. New code should pattern-match on
    the dataclass fields directly.
    """
    backend: str
    handler_kind: str
    fell_back_from: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.fell_back_from is not None

    def __str__(self) -> str:
        """Legacy magic-string format.

        Returned by `str(outcome)` and by lazy-format log calls
        (`log.info("used: %s", outcome)`). Round-9 introduced a
        DeprecationWarning here, but round-10 found that lazy-%s
        formatting in production logs would emit those warnings on
        every INFO line -- defeating the shim's purpose. So `__str__`
        is now silent: it just produces the legacy wire format.
        Migration is encouraged via the `startswith` shim's warning
        (which is a more deliberate API surface) and via the field
        comparisons documented in `ComposeOutcome`'s docstring.
        Round-10 python-reviewer MEDIUM + UX H3.
        """
        return self._format_legacy()

    def _format_legacy(self) -> str:
        """The legacy wire format without any deprecation noise.

        Used by `__str__` and by `startswith`. Tests that need to
        verify the shim's exact format call this directly so they
        don't have to muck with `warnings.simplefilter`.
        """
        if self.backend == "outlook" and not self.is_fallback:
            return "outlook"
        if self.is_fallback:
            return f"default:{self.handler_kind}:fallback-from-{self.fell_back_from}"
        return f"default:{self.handler_kind}"

    def startswith(self, prefix: str) -> bool:
        """DEPRECATED compatibility shim for `outcome.startswith("default:")`.

        Use field comparisons instead, e.g.::

            if outcome.backend == "outlook" and not outcome.is_fallback: ...
            if outcome.is_fallback: ...

        This shim still emits a `DeprecationWarning` because explicit
        `.startswith` calls are usually deliberate -- worth nudging.
        Removal target: bundle 30+.
        """
        warnings.warn(
            "ComposeOutcome.startswith is deprecated. Replace "
            "`outcome.startswith('default:')` with "
            "`outcome.backend != 'outlook' or outcome.is_fallback`, "
            "and `outcome.startswith('outlook')` with "
            "`outcome.backend == 'outlook' and not outcome.is_fallback`. "
            "Removal target: bundle 30+.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._format_legacy().startswith(prefix)


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
            cc: str | None = None,
            to: str | None = None,
            from_addr: str | None = None,
            reply_to: str | None = None,
            attachments=(),
            ) -> ComposeOutcome:
    """Open an email draft. Returns a `ComposeOutcome`.

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
        html=html, subject=subject,
        bcc=bcc, cc=cc, to=to,
        from_addr=from_addr, reply_to=reply_to,
        attachments=tuple(attachments) if attachments else (),
        preview_path=preview_path,
        handler=handler,
    )

    try:
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
        fallback.compose(draft)
        return ComposeOutcome(
            backend=fallback.name,
            handler_kind=handler.kind,
            fell_back_from=chosen.name,
        )

    return ComposeOutcome(backend=chosen.name, handler_kind=handler.kind)


__all__ = [
    "ComposeOutcome",
    "DraftEmail",
    "MailBackend",
    "MailHandler",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
    "detect_default_mail_handler",
]
# `load_recipients` is intentionally NOT re-exported -- it's not a
# mail-backend concern. New code imports from `scripts.recipients`.
# `is_available` (from outlook.py) is also not re-exported -- it's a
# backend-internal helper that collides conceptually with the
# `MailBackend.is_available()` method on the Protocol. Backends that
# need to expose availability do so via the Protocol method.
