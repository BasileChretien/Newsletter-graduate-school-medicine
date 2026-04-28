"""Small text-sanitization primitives shared by the recipients reader,
the subject-line builder, and the validator.

All three need to defend against the same Word-paste hazards:

* U+200B ZERO WIDTH SPACE / U+FEFF BOM / U+2060 WORD JOINER hidden
  inside an editor-pasted string -- the address that reads correctly
  in the editor's text file resolves to a different one in Outlook.
* U+202E RIGHT-TO-LEFT OVERRIDE smuggled mid-string -- visible reading
  order ≠ logical character order, so a recipient sees a different
  subject than what was logged.
* U+00A0 NBSP swapped in for ASCII space by Word's auto-format -- our
  unfilled-masthead `"VOL. XX"` token misses, the email ships with
  literal placeholder text in the subject preview.

Both fixes use the same NFKC + invisible-strip pipeline; collecting it
here keeps the three call sites in lockstep.
"""

from __future__ import annotations

import re
import unicodedata


# Unicode "Cf" (format) and "Cc" (control) categories cover ZWSP, ZWNJ,
# ZWJ, LRM, RLM, LRE, RLE, LRO, RLO, PDF, WJ, BOM, etc., plus C0/C1
# controls. We keep `\n` and `\t` because some legitimate body text
# contains them; the subject sanitizer collapses them via the
# `\s+` -> single-space pass below.
_KEEP_CONTROLS = {"\n", "\t", "\r"}


def strip_invisibles(s: str) -> str:
    """Drop Unicode invisible/bidi/control characters from `s`.

    Keeps `\\n` / `\\t` / `\\r` so callers that operate on multi-line
    input (e.g. body text) don't lose structure -- those are handled
    separately if/when the caller normalizes whitespace.
    """
    return "".join(
        ch for ch in s
        if ch in _KEEP_CONTROLS or
        unicodedata.category(ch) not in {"Cf", "Cc"}
    )


def normalize_compatibility(s: str) -> str:
    """NFKC-normalize: folds NBSP to space, fullwidth digits to ASCII, etc."""
    return unicodedata.normalize("NFKC", s)


def sanitize_subject(s: str) -> str:
    """Sanitize a single-line subject string.

    Pipeline: NFKC -> drop invisibles/controls -> collapse whitespace
    runs -> strip. Output is safe to put on the wire; recipients see
    exactly what the editor sees in the source.
    """
    s = normalize_compatibility(s)
    s = strip_invisibles(s)
    return re.sub(r"\s+", " ", s).strip()


__all__ = [
    "strip_invisibles",
    "normalize_compatibility",
    "sanitize_subject",
]
