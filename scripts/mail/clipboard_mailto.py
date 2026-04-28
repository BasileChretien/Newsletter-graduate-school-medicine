"""Cross-platform fallback backend.

Copies HTML to the system clipboard (CF_HTML on Windows, AppleScript
«class HTML» via temp file on macOS, xclip / wl-copy on Linux), then
opens the OS default mailto: handler with the subject pre-filled. The
editor pastes with Ctrl+V into the message body.
"""

from __future__ import annotations

import logging
import urllib.parse
import webbrowser

from scripts.mail.base import DraftEmail, MailHandler
from scripts.mail.clipboard import copy_html_to_clipboard

log = logging.getLogger(__name__)


def compose_via_default(draft: DraftEmail, *,
                        handler: MailHandler | None = None) -> None:
    """Copy HTML to clipboard and launch the OS default mail handler."""
    copied = copy_html_to_clipboard(draft.html)
    mailto = "mailto:?subject=" + urllib.parse.quote(draft.subject)
    webbrowser.open(mailto)
    if draft.preview_path is not None and draft.preview_path.exists():
        webbrowser.open(draft.preview_path.as_uri())
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


class ClipboardMailtoBackend:
    """MailBackend implementation that always works -- the universal fallback."""

    name = "clipboard_mailto"

    def is_available(self) -> bool:
        return True

    def matches(self, handler: MailHandler) -> bool:
        # Universal fallback -- accepts any handler.
        return True

    def compose(self, draft: DraftEmail, *,
                handler: MailHandler | None = None) -> None:
        compose_via_default(draft, handler=handler)


__all__ = ["compose_via_default", "ClipboardMailtoBackend"]
