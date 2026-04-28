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
# LRM, RLM, LRE, RLE, LRO, RLO, PDF, WJ, BOM, etc., plus C0/C1 controls.
#
# Preserved characters by default:
#   * `\n`, `\t`        -- legitimate structural whitespace; downstream
#                          callers collapse to single space if needed.
#
# `\r` is intentionally NOT preserved: it's harmful in subject lines
# (would let an injected CR survive into Outlook COM property
# assignment) and unhelpful elsewhere -- the recipients reader splits
# on lines BEFORE this function runs, so a stray `\r` mid-string is
# always a paste artefact, never a real line break.
#
# ZWJ (U+200D) used to be preserved here for compound emoji rendering,
# but the recipients reader feeds the SAME helper into `_EMAIL_RE` --
# and ZWJ isn't whitespace nor in the regex's exclusion class, so a
# crafted `victim<ZWJ>@evil.com` would pass validation and route to
# Outlook BCC. Round-9 security finding (MEDIUM 6). For body text /
# subjects that legitimately need ZWJ (which the toolkit doesn't
# generate today), use `strip_invisibles(s, keep_zwj=True)`.
_KEEP_CHARS = frozenset({"\n", "\t"})
_ZWJ = "‍"
_STRIP_CATEGORIES = frozenset({"Cf", "Cc"})


def strip_invisibles(s: str, *, keep_zwj: bool = False) -> str:
    """Drop Unicode invisible/bidi/control characters from `s`.

    Preserves `\\n` and `\\t` always. All other Cf/Cc category characters
    -- ZWSP, BOM, RLO, LRM, RLE, ZWJ, etc. -- are removed by default.

    Pass `keep_zwj=True` when the caller needs to preserve compound-emoji
    or Indic-script joiner sequences (e.g. rendering body text). Address
    validators MUST leave `keep_zwj=False` so a crafted ZWJ-bearing
    address can't smuggle past `_EMAIL_RE`.
    """
    keep: frozenset[str] = (
        _KEEP_CHARS | {_ZWJ} if keep_zwj else _KEEP_CHARS
    )
    return "".join(
        ch for ch in s
        if ch in keep or unicodedata.category(ch) not in _STRIP_CATEGORIES
    )


def normalize_compatibility(s: str) -> str:
    """NFKC-normalize: folds NBSP to space, fullwidth digits to ASCII, etc."""
    return unicodedata.normalize("NFKC", s)


def normalize_for_match(s: str) -> str:
    """Pipeline shared by the subject sanitizer and the validator's
    masthead-token check: NFKC-fold + collapse runs of whitespace
    (no leading/trailing strip, so callers that do substring matching
    on the result preserve token boundaries).

    Use this whenever you need to compare user-provided text against
    a fixed-string token in a way that's robust to NBSP, fullwidth
    punctuation, and double-spacing artefacts from Word.
    """
    return re.sub(r"\s+", " ", normalize_compatibility(s))


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
    "normalize_for_match",
    "sanitize_subject",
]
