"""Load and validate the editor's saved recipient list (`recipients.txt`).

This is a tiny standalone module rather than living in `scripts.mail`
because reading a list of e-mail addresses isn't a mail-backend concern.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from scripts.text_utils import normalize_compatibility, strip_invisibles

log = logging.getLogger(__name__)


# Loose RFC 5322 -- enough to reject obvious typos plus header/separator
# injection (`;`, `,`, CR/LF) without overfitting on valid edge cases.
_EMAIL_RE = re.compile(r"^[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+$")
# Hard ceiling -- a runaway recipients.txt cannot generate a 50 MB BCC.
_MAX_RECIPIENTS = 1000

# Invisible / bidi character handling delegates to `scripts.text_utils`
# so the recipients list, the subject-line builder, and the validator
# all defend against the same Word-paste hazards in lockstep.


def sanitize_addresses(values: Iterable[str]) -> tuple[list[str], list[str]]:
    """Normalize and validate address strings. Returns (accepted, rejected).

    Extracted from `load_recipients` so that EVERY path which can put an
    address into an outgoing draft gets the same guard -- not just the
    `recipients.txt` one. The browser build takes addresses typed into a
    textarea, and without this it inherited none of the protections
    below:

      * CR/LF in an address makes `EmailMessage` raise `ValueError`
        ("Header values may not contain linefeed or carriage return"),
        which surfaced to the editor as an unexplained crash.
      * `;` / `,` / `<` / `>` inside a single entry means one line can
        expand into several recipients, or (via the display-name form
        `Name <a@x>; Name2 <b@y>`) silently collapse a list down to its
        first entry once RFC 5322 parses the `;` as a group terminator.
      * Fullwidth `＠` and invisible characters (ZWSP, BOM, RLO) are
        folded first, so a Word-pasted address cannot smuggle past the
        pattern.

    Comment lines (`#`) and blanks are skipped silently -- they are
    expected in a `recipients.txt`, and harmless anywhere else.
    """
    seen: set[str] = set()
    accepted: list[str] = []
    rejected: list[str] = []
    for raw in values:
        # NFKC FIRST so fullwidth ASCII variants get folded before the
        # regex sees them. Round-10 security MEDIUM: a crafted
        # `victim<U+FF20>evil.com` (FULLWIDTH COMMERCIAL AT) would
        # otherwise pass `_EMAIL_RE` because `[^@\s;,<>]` only excludes
        # ASCII `@` (U+0040). NFKC folds `<U+FF20>` -> `@`, after
        # which the regex sees the address it would have otherwise
        # missed. Same logic applies to fullwidth digits, periods, etc.
        # THEN strip invisibles so a hidden ZWSP / BOM / RLO doesn't
        # survive validation.
        line = strip_invisibles(
            normalize_compatibility(raw)
        ).strip().rstrip(",").strip()
        if not line or line.startswith("#"):
            continue
        if not _EMAIL_RE.match(line):
            rejected.append(line)
            continue
        if line in seen:
            continue
        seen.add(line)
        accepted.append(line)
        if len(accepted) >= _MAX_RECIPIENTS:
            break
    return accepted, rejected


def load_recipients(recipients_path: Path) -> list[str]:
    """Read a `recipients.txt` -- one address per line, # comments allowed.

    Validation lives in `sanitize_addresses`; this function adds the
    file reading and the editor-facing warnings. Result is deduplicated
    and capped at `_MAX_RECIPIENTS` entries.
    """
    if not recipients_path.exists():
        return []
    accepted, rejected = sanitize_addresses(
        recipients_path.read_text(encoding="utf-8").splitlines())
    for line in rejected:
        log.warning(
            "Skipped one address from recipients.txt that didn't "
            "look right: %r (the rest are fine).", line)
    if len(accepted) >= _MAX_RECIPIENTS:
        log.warning(
            "recipients.txt has more than %d entries -- truncated.",
            _MAX_RECIPIENTS)
    return accepted


__all__ = ["load_recipients", "sanitize_addresses"]
