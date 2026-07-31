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
# Pre-computed once at module load so `keep_zwj=True` callers don't
# allocate a new frozenset on every invocation (round-10
# python-reviewer HIGH). `frozenset | frozenset` returns a new
# frozenset; doing it on every call costs ~200ns plus GC pressure.
_KEEP_CHARS_WITH_ZWJ = _KEEP_CHARS | frozenset({_ZWJ})
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
    keep = _KEEP_CHARS_WITH_ZWJ if keep_zwj else _KEEP_CHARS
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


# URL schemes allowed to reach a recipient. Everything else -- `file:`,
# `javascript:`, `data:`, `vbscript:`, `ms-msdt:`, `search-ms:` and every
# other registered protocol handler -- is dropped.
#
# This lives here, not in `scripts/mail/plaintext.py` where it started,
# because the plaintext part was the ONLY place it was applied. The HTML
# part -- the one recipients actually render -- shipped whatever scheme
# the DOCX contained. `file://host/share/x` is the sharp end: clicked in
# Outlook on a domain-joined Windows machine it is a UNC path, so the
# recipient's workstation authenticates to the attacker over SMB and
# leaks a NetNTLMv2 hash. The mail comes from the editor's own mailbox,
# so it passes SPF/DKIM/DMARC and reads as trusted internal post.
#
# Worse, the two MIME alternatives disagreed: the plaintext part stripped
# the hostile target while the HTML part kept it, so a plaintext client,
# an archive review or a DLP scan all saw clean prose.
SAFE_URL_SCHEMES: tuple[str, ...] = ("http://", "https://", "mailto:")


def is_safe_url_scheme(href: str) -> bool:
    """True when `href` may be shown to a recipient as a live link.

    Normalizes before deciding, because the raw string is
    attacker-controlled: NFKC folds fullwidth variants, invisible
    characters are stripped (`java<ZWSP>script:`), leading control
    characters and whitespace are removed (`\\x01javascript:`), and the
    comparison is case-insensitive. Each of those is a documented filter
    bypass, so the check has to run on the normalized form rather than
    on what the document claims to contain.

    A relative or anchor-only href (`#section`, `/page`) has no scheme
    and is treated as unsafe: nothing in this toolkit emits one, and in
    an email there is no base URL for it to resolve against.
    """
    cleaned = strip_invisibles(normalize_compatibility(href or ""))
    # Control characters are ignored by URL parsers but not by a naive
    # prefix check, so drop them rather than merely trimming whitespace.
    cleaned = "".join(
        c for c in cleaned if unicodedata.category(c) not in ("Cc", "Cf")
    ).strip().lower()
    return cleaned.startswith(SAFE_URL_SCHEMES)


__all__ = [
    "SAFE_URL_SCHEMES",
    "is_safe_url_scheme",
    "strip_invisibles",
    "normalize_compatibility",
    "normalize_for_match",
    "sanitize_subject",
]
