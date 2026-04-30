"""Public types shared by every mail backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.mail.cid import InlineImage


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
    """Pure-data description of an email draft to open in a client.

    All recipient/header fields are optional so a backend can ignore
    what it doesn't support (e.g. mailto: only honours `subject` + `bcc`,
    not `from_addr`). Adding fields here BEFORE more backends arrive
    avoids breaking-change refactors of every backend later.
    """

    html: str
    subject: str
    bcc: str | None = None
    cc: str | None = None
    to: str | None = None
    from_addr: str | None = None     # optional From: -- shared mailbox / department address
    reply_to: str | None = None
    attachments: tuple[Path, ...] = field(default_factory=tuple)
    # Inline-image attachment specs for the CID image-mode. Backends
    # that don't know how to inline-attach (clipboard_mailto) MUST
    # ignore this field; only `OutlookBackend` consumes it. The HTML
    # in `html` is already CID-rewritten when this is non-empty.
    inline_images: "tuple[InlineImage, ...]" = field(default_factory=tuple)
    preview_path: Path | None = None
    # Identifies the OS-detected default mail client (when known) so a
    # backend can use it for log messages without a back-channel call.
    handler: MailHandler | None = None


class MailBackend(Protocol):
    """Strategy for opening an email-draft window.

    Concrete backends live in `scripts/mail/<name>.py` and are added to
    `scripts.mail._BACKENDS` in priority order. The Protocol is
    structurally typed -- implementations don't `class Foo(MailBackend)`
    explicitly; they just expose `name`, `is_available`, `matches`, and
    `compose` with matching signatures.
    """

    name: str

    def is_available(self) -> bool: ...

    def matches(self, handler: MailHandler) -> bool: ...

    def compose(self, draft: DraftEmail) -> None: ...


__all__ = ["MailHandler", "DraftEmail", "MailBackend"]
