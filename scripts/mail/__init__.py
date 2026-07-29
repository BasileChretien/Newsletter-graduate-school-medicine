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
    select_backend(name, handler) -> MailBackend
    resolve_image_mode(image_mode, handler, backend) -> str
    compose(html, *, subject, backend="auto", preview_path=None,
            bcc=None, to=None) -> ComposeOutcome
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.mail.base import DraftEmail, MailBackend, MailHandler
from scripts.mail.cid import InlineImage, attach_inline_images
from scripts.mail.clipboard import copy_html_to_clipboard
from scripts.mail.clipboard_mailto import (
    ClipboardMailtoBackend, compose_via_default,
)
from scripts.mail.detect import detect_default_mail_handler
from scripts.mail.eml import EmlBackend, build_eml, eml_path_for, write_eml
from scripts.mail.outlook import OutlookBackend, compose_outlook
from scripts.recipients import load_recipients

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComposeOutcome:
    """Typed result of a `compose()` call.

    Replaces the round-7 stringly-typed return (`"outlook"`,
    `"default:apple_mail"`, `"default:browser:fallback-from-outlook"`)
    with explicit fields:

    * `backend`         -- name of the backend that actually composed
                           the draft (`"outlook"`, `"clipboard_mailto"`).
    * `handler_kind`    -- detected default-mail-handler kind
                           (`"outlook"`, `"apple_mail"`, `"thunderbird"`,
                           `"browser"`, `"other"`, `"unknown"`).
    * `fell_back_from`  -- if the auto-path attempted Outlook and it
                           threw, this holds `"outlook"`. None otherwise.
    * `image_mode`      -- the concrete image mode that was actually
                           used (`"cid"` or `"url"`). When the caller
                           passed `"auto"`, this carries the resolved
                           value; on auto-fallback from Outlook to the
                           clipboard backend, the value is `"url"`
                           (CID requires Outlook). Round-13 architect
                           HIGH 2.

    `__str__` preserves the legacy magic-string wire format so
    existing log lines and any string-comparing call sites keep
    working during the migration. New code should pattern-match on
    the dataclass fields directly.
    """
    backend: str
    handler_kind: str
    fell_back_from: str | None = None
    image_mode: str | None = None

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


# The universal fallback. Named explicitly rather than addressed as
# `_BACKENDS[-1]`: with only two entries the positional form was
# harmless, but it turns "append a new backend to the registry" into a
# silent redefinition of what the auto-path falls back to.
_FALLBACK_BACKEND: MailBackend = ClipboardMailtoBackend()

# Registry: ordered, priority high-to-low. The dispatcher iterates and
# stops at the first backend whose `matches(handler)` returns True AND
# whose `is_available()` returns True.
_BACKENDS: list[MailBackend] = [
    OutlookBackend(),      # Windows + Outlook desktop -- rich HTML draft
    EmlBackend(),          # explicit `--backend=eml` only; matches() is False
    _FALLBACK_BACKEND,     # universal fallback
]

# Backends that can embed photos as MIME parts. Derived from the
# registry rather than hand-listed so a new CID-capable backend is
# picked up by `resolve_image_mode` automatically.
_CID_CAPABLE_NAMES: frozenset[str] = frozenset(
    b.name for b in _BACKENDS if b.supports_inline_images
)


BackendName = Literal["auto", "outlook", "default", "eml"]


def image_mode_key(chosen: MailBackend) -> str:
    """Map a chosen backend to the vocabulary `resolve_image_mode` speaks.

    `resolve_image_mode`'s `backend` argument is CLI-level
    (`"auto"` / `"outlook"` / `"default"` / `"eml"`), while the
    dispatcher works in backend identities (`"clipboard_mailto"`).
    Every call site needs the same translation, so it lives here once
    instead of being re-spelled as an inline conditional in three
    files -- which is how the two paths drifted apart in round 15.
    """
    return chosen.name if chosen.name in _CID_CAPABLE_NAMES else "default"


def select_backend(name: BackendName, handler: MailHandler) -> MailBackend:
    """Pick a backend by explicit name or auto-detect.

    Public since round-15: `build_newsletter.py:all_cmd` needs to know
    which backend will actually be used BEFORE running the build, so
    it can refuse `--image-mode=cid` early when the chosen backend
    can't attach inline images. Prior to round-15 this was private
    and `all_cmd` peeked at `handler.is_outlook_desktop` instead --
    which diverged from the dispatcher's real choice when
    `OutlookBackend.is_available()` returned False on a Windows box
    with a partial pywin32 install (round-15 architect HIGH 1).

    Pure (no I/O, no state mutation), so callers can call it cheaply
    to peek at the dispatcher's decision without committing to a send.
    """
    if name == "auto":
        for backend in _BACKENDS:
            if backend.matches(handler) and backend.is_available():
                return backend
        # Universal fallback always matches; ClipboardMailtoBackend wins.
        # `EmlBackend.matches()` is False, so `auto` never lands there --
        # `.eml` is an explicit choice, never a surprise.
        return _FALLBACK_BACKEND
    if name == "outlook":
        return next(b for b in _BACKENDS if b.name == "outlook")
    if name == "eml":
        return next(b for b in _BACKENDS if b.name == "eml")
    if name == "default":
        return next(b for b in _BACKENDS if b.name == "clipboard_mailto")
    raise ValueError(
        f"backend must be 'auto', 'outlook', 'eml' or 'default' -- "
        f"got {name!r}")


def resolve_image_mode(image_mode: str, handler: MailHandler,
                       backend: str = "auto") -> str:
    """Resolve `image_mode='auto'` to a concrete `'cid'` or `'url'`.

    Single source of truth for the auto-resolution rule. Both
    `compose()` (downstream) and the CLI's `all` command (upstream,
    so it can decide whether to publish photos to GitHub) call this
    so the two paths can never disagree -- closing round-13 architect
    HIGH 1 ("resolution-logic divergence").

    The rule:
      * `auto` + the chosen backend can embed images -> `cid`
        (that means Outlook desktop, or an explicit `--backend=eml`)
      * `auto` + anything else                       -> `url`
      * explicit `cid` / `url`                       -> passthrough

    `backend` reflects the user's `--backend` selection. `auto` here
    means "auto-detect", which lines up with `select_backend`'s rule
    of preferring Outlook on Windows when it matches. Explicit
    `--backend=outlook` on a non-Outlook handler is honoured (the
    user is forcing the issue), and we still resolve to `cid` so the
    explicit-route gets the right image mode -- the validation in
    `compose()` will then check feasibility.
    """
    if image_mode in ("cid", "url"):
        return image_mode
    if image_mode != "auto":
        raise ValueError(
            f"image_mode must be 'url', 'cid', or 'auto' -- got "
            f"{image_mode!r}"
        )
    # auto: a CID-capable backend gets cid, anyone else url.
    will_embed_images = (
        backend in _CID_CAPABLE_NAMES
        or (backend == "auto" and handler.is_outlook_desktop)
    )
    return "cid" if will_embed_images else "url"


def compose(html: str, *, subject: str, backend: str = "auto",
            preview_path: Path | None = None,
            bcc: str | None = None,
            cc: str | None = None,
            to: str | None = None,
            from_addr: str | None = None,
            reply_to: str | None = None,
            attachments=(),
            image_mode: str = "auto",
            asset_dir: Path | None = None,
            ) -> ComposeOutcome:
    """Open an email draft. Returns a `ComposeOutcome`.

    Image-handling modes (`image_mode`):

    * `"auto"` (default, **Phase 2**) -- pick the best mode for the
      chosen backend. A backend that can embed photos as MIME parts
      (`supports_inline_images`: Outlook desktop, or an explicit
      `--backend=eml`) -> `"cid"`, which is the most robust against
      corporate filters that quarantine `raw.githubusercontent.com`
      and removes the requirement for the editor to have a GitHub
      account. Anything else -> `"url"` (the clipboard / mailto path
      has nowhere to put an attachment).
    * `"cid"` -- explicit CID. HTML images that resolve to local
      files under `asset_dir` are CID-rewritten and attached to the
      message via MIME `multipart/related`. Requires a backend whose
      `supports_inline_images` is True; raises `ValueError` otherwise.
    * `"url"` -- explicit URL. HTML's `<img src="https://...">`
      references are sent as-is; recipients' clients fetch images at
      display time. The pre-Phase-1 default; useful for forks at
      institutions where Outlook isn't the dominant client.

    Failure modes:
      - `backend="outlook"` explicit + Outlook throws  -> re-raise.
        Caller MUST surface this to the editor so they don't think the
        BCC list silently went out via clipboard.
      - `backend="auto"` + Outlook throws -> warn loudly (so the editor
        notices the change), then fall back to the clipboard backend
        with `image_mode` re-resolved to `"url"` and the original
        URL HTML.
    """
    handler = detect_default_mail_handler()
    log.info("Default mail handler: %s [%s]", handler.name, handler.kind)

    chosen = select_backend(backend, handler)

    # Resolve `auto` via the shared helper -- the SAME helper `all_cmd`
    # calls when it's deciding whether to skip `publish-images`, so the
    # two paths can never disagree. Round-13 architect HIGH 1.
    # We feed the helper a synthetic backend identity that matches the
    # dispatcher's actual choice (`chosen.name`) rather than the user's
    # raw `backend` string: that way `--backend=auto` on a non-Outlook
    # box where Outlook would have been preferred but is unavailable
    # still resolves to URL (matching the real dispatch).
    image_mode = resolve_image_mode(
        image_mode, handler, backend=image_mode_key(chosen),
    )

    inline_images: tuple[InlineImage, ...] = ()
    # Round-12 architect HIGH 2: keep the un-rewritten URL HTML around
    # so that if the Outlook backend fails AND we auto-fall-back to
    # ClipboardMailto, the recipient doesn't paste a `<img src="cid:..."`
    # body that the clipboard backend has no way to resolve. The
    # fallback path receives the original URL HTML.
    original_url_html = html
    if image_mode == "cid":
        if not chosen.supports_inline_images:
            raise ValueError(
                "image_mode='cid' needs a backend that can embed "
                "photos as MIME parts, but "
                f"{chosen.name!r} was selected. Use --backend=outlook "
                "(Outlook desktop), --backend=eml (writes a .eml draft "
                "file), or --image-mode=url for the hosted-photo path."
            )
        if asset_dir is None:
            raise ValueError(
                "image_mode='cid' requires asset_dir to be passed "
                "(the local directory holding the issue's photos)."
            )
        html, inline_images = attach_inline_images(html, asset_dir)
        log.info("CID mode: %d inline image(s) prepared for attachment.",
                 len(inline_images))

    draft = DraftEmail(
        html=html, subject=subject,
        bcc=bcc, cc=cc, to=to,
        from_addr=from_addr, reply_to=reply_to,
        attachments=tuple(attachments) if attachments else (),
        inline_images=inline_images,
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
        # Round-12 architect HIGH 2: rebuild the DraftEmail with the
        # original URL HTML and NO inline images so the clipboard
        # backend hands the editor a body that resolves cleanly --
        # `cid:` references would be broken once Outlook is out of
        # the picture.
        fallback_draft = DraftEmail(
            html=original_url_html, subject=subject,
            bcc=bcc, cc=cc, to=to,
            from_addr=from_addr, reply_to=reply_to,
            attachments=tuple(attachments) if attachments else (),
            preview_path=preview_path,
            handler=handler,
        )
        fallback = _FALLBACK_BACKEND
        fallback.compose(fallback_draft)
        return ComposeOutcome(
            backend=fallback.name,
            handler_kind=handler.kind,
            fell_back_from=chosen.name,
            # Auto-fallback always lands on URL mode -- the clipboard
            # backend cannot attach files (CID needs Outlook COM), and
            # we hand it the original_url_html above.
            image_mode="url",
        )

    return ComposeOutcome(
        backend=chosen.name,
        handler_kind=handler.kind,
        image_mode=image_mode,
    )


__all__ = [
    "ComposeOutcome",
    "DraftEmail",
    "EmlBackend",
    "MailBackend",
    "MailHandler",
    "build_eml",
    "compose",
    "compose_outlook",
    "compose_via_default",
    "copy_html_to_clipboard",
    "detect_default_mail_handler",
    "eml_path_for",
    "image_mode_key",
    "resolve_image_mode",
    "select_backend",
    "write_eml",
]
# `load_recipients` is intentionally NOT re-exported -- it's not a
# mail-backend concern. New code imports from `scripts.recipients`.
# `is_available` (from outlook.py) is also not re-exported -- it's a
# backend-internal helper that collides conceptually with the
# `MailBackend.is_available()` method on the Protocol. Backends that
# need to expose availability do so via the Protocol method.
