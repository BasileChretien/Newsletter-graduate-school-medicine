"""Load and validate the editor's saved recipient list (`recipients.txt`).

This is a tiny standalone module rather than living in `scripts.mail`
because reading a list of e-mail addresses isn't a mail-backend concern.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)


# Loose RFC 5322 -- enough to reject obvious typos plus header/separator
# injection (`;`, `,`, CR/LF) without overfitting on valid edge cases.
_EMAIL_RE = re.compile(r"^[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+$")
# Hard ceiling -- a runaway recipients.txt cannot generate a 50 MB BCC.
_MAX_RECIPIENTS = 1000


def load_recipients(recipients_path: Path) -> list[str]:
    """Read a `recipients.txt` -- one address per line, # comments allowed.

    Each non-comment line is validated against a loose RFC 5322 pattern and
    rejected if it contains a separator character (`;`, `,`, CR/LF) that
    Outlook's BCC parser would split on -- prevents a malicious or typo'd
    line from expanding into multiple recipients. Result is deduplicated
    and capped at _MAX_RECIPIENTS entries.
    """
    if not recipients_path.exists():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in recipients_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().rstrip(",").strip()
        if not line or line.startswith("#"):
            continue
        if not _EMAIL_RE.match(line):
            log.warning(
                "Skipping invalid recipient (not a valid e-mail address "
                "or contains a separator character): %r", line)
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= _MAX_RECIPIENTS:
            log.warning(
                "recipients.txt has more than %d entries -- truncated.",
                _MAX_RECIPIENTS)
            break
    return out


__all__ = ["load_recipients"]
