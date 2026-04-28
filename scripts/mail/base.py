"""Public types shared by every mail backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MailHandler:
    """Identifies the user's default email client."""

    kind: str        # "outlook" | "apple_mail" | "thunderbird" | "browser" | "other" | "unknown"
    name: str        # human-readable name from the OS
    raw_id: str = "" # OS-level identifier

    @property
    def is_outlook_desktop(self) -> bool:
        return self.kind == "outlook"


@dataclass(frozen=True)
class DraftEmail:
    """Pure-data description of an email draft to open in a client."""

    html: str
    subject: str
    bcc: str | None = None
    to: str | None = None
    preview_path: Path | None = None


class MailBackend(Protocol):
    """Strategy for opening an email-draft window.

    Implementers register themselves in `scripts.mail._BACKENDS` (or just
    expose a top-level `name` and `is_available()` and `compose(draft)`).
    """

    name: str

    def is_available(self) -> bool: ...

    def matches(self, handler: MailHandler) -> bool: ...

    def compose(self, draft: DraftEmail) -> None: ...


__all__ = ["MailHandler", "DraftEmail", "MailBackend"]
