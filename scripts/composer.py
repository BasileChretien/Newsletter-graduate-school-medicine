"""Backwards-compatible facade for the mail-backend package.

The implementation now lives in `scripts.mail.*` -- see scripts/mail/
for the strategy/Protocol decomposition. This module re-exports the
same public API so existing callers and tests continue to work.
"""

from __future__ import annotations

from scripts.mail import (
    MailHandler,
    compose,
    compose_outlook,
    compose_via_default,
    copy_html_to_clipboard,
    detect_default_mail_handler,
    load_recipients,
)
from scripts.mail.outlook import is_available as _outlook_com_available


__all__ = [
    "MailHandler",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
    "detect_default_mail_handler",
    "load_recipients",
]
