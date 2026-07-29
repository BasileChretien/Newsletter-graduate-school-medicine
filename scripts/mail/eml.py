"""`.eml` export backend -- a real RFC 5322 draft file on disk.

Why this exists
---------------
The two shipping backends are OS-bound in opposite ways:

* `OutlookBackend` produces a perfect draft (subject, BCC, CID photos
  embedded) but needs Windows + pywin32 + Outlook desktop COM.
* `ClipboardMailtoBackend` works everywhere but hands the editor a
  clipboard and asks them to paste -- and paste is exactly where
  formatting and images break. It is a fallback, not a destination.

This module fills the gap with a third option that is pure stdlib and
pure data: serialize the draft to a `.eml` file. Opening that file in
Outlook desktop yields an editable, ready-to-send draft with the
subject filled, the BCC list filled, and the photos embedded as MIME
parts -- with no COM, no clipboard, and no paste step.

That makes it useful in three separate situations:

1. **A machine without Outlook COM.** Thunderbird ("Edit as New
   Message") and most Linux clients open a `.eml` for editing.
2. **An audit artefact.** The `.eml` is the exact bytes the recipients
   would receive; it can be archived next to `dist/issue-N.html`.
3. **A server- or browser-side build.** A hosted or WASM version of
   this toolkit cannot drive the editor's Outlook, but it *can* hand
   back a `.eml`. Returning HTML would put the editor back into
   copy/paste; returning `.eml` does not.

MIME structure
--------------
The canonical shape that Outlook, Thunderbird and Gmail all render::

    multipart/alternative
    |-- text/plain                 <- spam-filter friendly, real structure
    `-- multipart/related
        |-- text/html              <- <img src="cid:...">
        `-- image/jpeg (inline)    <- Content-ID: <...>

`multipart/mixed` wraps the whole thing only when there are ordinary
(non-inline) attachments.

Draft, not a received message
-----------------------------
`X-Unsent: 1` is the header Outlook uses to decide that a `.eml` is an
*unsent* message: it opens in compose mode with a Send button rather
than in the read-only reading pane. Thunderbird ignores it (use
"Edit as New Message"), and Apple Mail ignores it too -- see the
caveat in `EmlBackend`'s docstring.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path

from scripts.image_handler import extension_to_mime
from scripts.mail.base import DraftEmail, MailHandler
from scripts.mail.cid import InlineImage
from scripts.mail.plaintext import (
    html_to_plaintext, html_to_plaintext_strict_fallback,
)

log = logging.getLogger(__name__)


# Outlook's "this is a draft, not a received message" marker. Without
# it the editor gets a read-only reading-pane window with no Send
# button, which defeats the whole point of the export.
_X_UNSENT_HEADER = "X-Unsent"
_X_UNSENT_VALUE = "1"

# `email.policy.SMTP` serializes with CRLF line endings (RFC 5322 §2.3)
# and does RFC 2047 header encoding for non-ASCII subjects -- both
# required for a file that third-party mail clients will parse. The
# default policy uses bare LF, which some strict parsers reject.
_POLICY = SMTP


_ADDRESS_SEPARATOR_RE = re.compile(r"[;,]")


def _rfc5322_address_list(value: str) -> str:
    r"""Normalize a recipient list to the comma separator RFC 5322 requires.

    The toolkit joins recipients with `"; "` because that is what
    Outlook's COM `BCC` property expects. RFC 5322 uses commas, and a
    semicolon means something else entirely: `group-name: a@x, b@y;`.
    So `msg["Bcc"] = "a@x; b@y"` under `email.policy.SMTP` parses as a
    malformed group and **silently keeps only the first address** --
    a 50-recipient newsletter would reach one person, with no error
    anywhere. Caught by `test_bcc_survives_a_full_fifty_recipient_list`.

    Splitting on `[;,]` is safe for this toolkit specifically because
    `scripts.recipients.load_recipients` rejects any address containing
    `;`, `,`, `<`, `>` or whitespace -- so there are no display names
    and no quoted strings to split through. As a guard for future
    callers that don't come from `recipients.txt`, a value that looks
    like it carries display-name syntax (`"` or `<`) is passed through
    untouched on the assumption the caller already formatted it.
    """
    if '"' in value or "<" in value:
        return value
    parts = (p.strip() for p in _ADDRESS_SEPARATOR_RE.split(value))
    return ", ".join(p for p in parts if p)


def _plaintext_alternative(html: str) -> str:
    """Build the `text/plain` part, mirroring the Outlook backend.

    Same two-tier strategy as `compose_outlook`: the structural
    converter first (headings, bullets, surfaced URLs), then the
    regex tag-stripper if that raises. A `multipart/alternative`
    message with a poor text part still scores far better with
    Mimecast / Proofpoint / Defender than an HTML-only one, so we
    never give up and ship HTML alone.
    """
    try:
        return html_to_plaintext(html)
    except Exception as e:  # noqa: BLE001 -- plaintext is best-effort
        log.warning(
            "html_to_plaintext failed (%s); falling back to strict "
            "tag-strip plaintext to keep multipart/alternative.", e,
        )
    try:
        return html_to_plaintext_strict_fallback(html)
    except Exception as e:  # noqa: BLE001 -- last resort
        log.warning(
            "Strict plaintext fallback also failed (%s); the .eml will "
            "carry an empty text part rather than no text part at all.",
            e,
        )
        return ""


def _attach_inline(html_part: EmailMessage, inline: InlineImage) -> bool:
    """Attach one CID image to the HTML part as a `multipart/related` sibling.

    Returns True when the part was added. A missing / unreadable file
    is logged and skipped rather than raised: the rest of the
    newsletter is still worth delivering, and the editor sees the
    warning in the launcher console.

    Note that only `inline.path.name` reaches the message -- never the
    absolute path. The editor's local directory layout is not the
    recipients' business (same reasoning as the Outlook backend
    clearing `PR_ATTACH_PATHNAME`).
    """
    try:
        data = inline.path.read_bytes()
    except OSError as e:
        log.warning(
            "Inline image %s could not be read (%s); the .eml will "
            "reference cid:%s with no matching part -- recipients "
            "would see a broken image.",
            inline.path, e, inline.cid,
        )
        return False
    mime = extension_to_mime(inline.path)
    maintype, _, subtype = mime.partition("/")
    if not subtype:
        maintype, subtype = "application", "octet-stream"
    html_part.add_related(
        data,
        maintype=maintype,
        subtype=subtype,
        # RFC 2392: `<img src="cid:foo@bar">` resolves against
        # `Content-ID: <foo@bar>`. `attach_inline_images` produces the
        # bare value, so the angle brackets are added here.
        cid=f"<{inline.cid}>",
        filename=inline.path.name,
        disposition="inline",
    )
    return True


def build_eml(draft: DraftEmail) -> EmailMessage:
    """Serialize a `DraftEmail` into an `EmailMessage`.

    Pure: reads the inline-image files from disk, but writes nothing
    and touches no OS mail client. `draft.html` is expected to already
    be CID-rewritten when `draft.inline_images` is non-empty (that
    rewriting happens in `scripts.mail.cid.attach_inline_images`,
    upstream in `compose()`).

    Header fields that are None are omitted entirely rather than
    written empty -- an empty `To:` header makes some clients refuse
    to open the file in compose mode.
    """
    msg = EmailMessage(policy=_POLICY)
    msg["Subject"] = draft.subject
    # Recipient lists arrive in Outlook's `"; "`-joined form; RFC 5322
    # needs commas. See `_rfc5322_address_list` -- getting this wrong
    # drops every recipient after the first, silently.
    if draft.to:
        msg["To"] = _rfc5322_address_list(draft.to)
    if draft.cc:
        msg["Cc"] = _rfc5322_address_list(draft.cc)
    if draft.bcc:
        msg["Bcc"] = _rfc5322_address_list(draft.bcc)
    if draft.from_addr:
        msg["From"] = draft.from_addr
    if draft.reply_to:
        msg["Reply-To"] = draft.reply_to
    msg[_X_UNSENT_HEADER] = _X_UNSENT_VALUE

    # Order matters: `set_content` establishes text/plain, then
    # `add_alternative` promotes the message to multipart/alternative
    # with the HTML second (clients pick the LAST part they can
    # render, so HTML must come after plaintext).
    msg.set_content(_plaintext_alternative(draft.html))
    msg.add_alternative(draft.html, subtype="html")

    if draft.inline_images:
        # payload[1] is the text/html part just added. Attaching the
        # images to THAT part (not to `msg`) is what produces the
        # `multipart/related` nesting the docstring describes.
        html_part = msg.get_payload()[1]
        attached = sum(
            1 for img in draft.inline_images if _attach_inline(html_part, img)
        )
        log.info(".eml: %d/%d inline image(s) embedded.",
                 attached, len(draft.inline_images))

    for path in draft.attachments or ():
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError as e:
            log.warning("Attachment %s could not be read (%s); skipped.", p, e)
            continue
        maintype, _, subtype = extension_to_mime(p).partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype,
                           filename=p.name)

    return msg


def eml_path_for(draft: DraftEmail) -> Path:
    """Where this draft's `.eml` belongs: next to the rendered HTML.

    `preview_path` is the `dist/issue-N.html` the build step wrote, so
    the export lands at `dist/issue-N.eml` -- same folder, same
    basename, obvious pairing for the editor. It also means
    `--output-dir` is honoured for free.

    Raises `ValueError` when `preview_path` is None rather than
    inventing a location: silently writing the editor's newsletter to
    a temp directory they will never find is worse than a clear error.
    """
    if draft.preview_path is None:
        raise ValueError(
            "The .eml backend needs to know where to write the file, "
            "which it derives from the rendered HTML's location "
            "(preview_path). Run `build` first so dist/issue-N.html "
            "exists, then re-run compose."
        )
    return Path(draft.preview_path).with_suffix(".eml")


def write_eml(draft: DraftEmail, path: Path | None = None) -> Path:
    """Build the message and write it to disk. Returns the path written."""
    out = Path(path) if path is not None else eml_path_for(draft)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_eml(draft).as_bytes())
    log.info("Wrote %s (%d bytes)", out, out.stat().st_size)
    return out


def open_with_default_app(path: Path) -> bool:
    """Hand `path` to the OS so the default mail client opens it.

    Best-effort by design -- the file is already on disk and the CLI
    prints its location, so a failure here costs the editor one
    double-click, not their work. Returns True when the OS accepted
    the request.
    """
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(path))  # noqa: S606 -- documented Windows API
            return True
        opener = "open" if system == "Darwin" else "xdg-open"
        if shutil.which(opener) is None:
            log.warning("No `%s` on PATH; open %s manually.", opener, path)
            return False
        subprocess.run([opener, str(path)], check=True, timeout=30)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Could not open %s automatically (%s). "
                    "Double-click it to open the draft.", path, e)
        return False


class EmlBackend:
    """MailBackend that writes a `.eml` draft and opens it.

    Never auto-selected: `matches()` returns False, so this backend is
    reachable only via an explicit `--backend=eml`. That is deliberate.
    Outlook desktop opens a `.eml` as a true editable draft, but
    **Apple Mail does not** -- it shows the file in a read-only viewer
    window, so a macOS editor would still have to forward or re-create
    the message. Until that path is verified on a real Mac, flipping
    any platform's default to `.eml` would be a regression dressed up
    as a fix. Making it the macOS default later is a one-line change
    to `matches()`.
    """

    name = "eml"
    # Consumed by `compose()` and `build_newsletter.py:all_cmd` to
    # decide whether `--image-mode=cid` is feasible. Declaring the
    # capability on the backend (rather than testing `name ==
    # "outlook"` at the call sites) is what stops the two paths from
    # drifting apart -- the exact divergence the round-15 audit found.
    supports_inline_images = True

    def is_available(self) -> bool:
        # Pure stdlib: no COM, no clipboard, no external binary.
        return True

    def matches(self, handler: MailHandler) -> bool:
        return False

    def compose(self, draft: DraftEmail) -> None:
        out = write_eml(draft)
        open_with_default_app(out)


__all__ = [
    "EmlBackend",
    "build_eml",
    "eml_path_for",
    "open_with_default_app",
    "write_eml",
]
