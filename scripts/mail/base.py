"""Public types shared by every mail backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MailHandler:
    """Identifies the user's default email client."""

    kind: str        # "outlook" | "apple_mail" | "thunderbird" | "browser" | "other" | "unknown"
    name: str        # human-readable name from the OS
    raw_id: str = "" # OS-level identifier

    @property
    def is_outlook_desktop(self) -> bool:
        return self.kind == "outlook"


__all__ = ["MailHandler"]
