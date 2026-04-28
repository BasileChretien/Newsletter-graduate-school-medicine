"""Inline CSS into HTML using css_inline (Rust-backed, fast).

After inlining, a small kept-as-<style> block carries rules that MUST
NOT be inlined -- @media queries (print, prefers-color-scheme), pseudo
states (Apple Mail x-apple-data-detectors), and a forced-colors safety
net for Outlook Windows high-contrast mode.
"""

from __future__ import annotations

import logging
from pathlib import Path

import css_inline

from scripts.config import TEMPLATES_DIR

log = logging.getLogger(__name__)


# Rules that survive the css_inline pass by being injected into <head>
# AFTER inlining. Email clients that strip <style> blocks (notably
# Gmail's classic webmail) lose these silently -- that's acceptable for
# print and forced-colors, both of which degrade gracefully.
_KEPT_STYLES: str = """
@media print {
  body, .container { background: #FFFFFF !important; }
  /* Round 8 Visual L3: don't waste ink on the cream masthead band
     and the 8px solid blue top-rule. A thin 1pt blue rule under the
     wordmark is plenty for a printed copy. */
  .masthead { background: #FFFFFF !important; border-top: 1pt solid #003F88 !important; }
  .footer { background: #FFFFFF !important; color: #1C1C1E !important; }
  .footer a { color: #003F88 !important; }
}
/* Apple Mail / iOS Mail: stop the OS auto-detecting dates and phone
   numbers, then re-styling them blue. format-detection meta covers
   most cases; this is the belt-and-braces. */
a[x-apple-data-detectors] {
  color: inherit !important;
  text-decoration: none !important;
  font-size: inherit !important;
  font-family: inherit !important;
  font-weight: inherit !important;
  line-height: inherit !important;
}
""".strip()


def inline(html: str, css_path: Path | None = None) -> str:
    """Return HTML with all stylesheet rules inlined as style attributes,
    plus a small kept-style block for rules that can't be inlined."""
    if css_path is None:
        css_path = TEMPLATES_DIR / "styles.css"
    extra_css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    inliner = css_inline.CSSInliner(
        extra_css=extra_css,
        keep_style_tags=False,
        load_remote_stylesheets=False,
    )
    inlined = inliner.inline(html)
    style_block = f"<style type=\"text/css\">{_KEPT_STYLES}</style>"

    # Inject before </head> for the common path (full HTML doc). Fall
    # back gracefully when the inliner returned a fragment / partial -- the
    # @media print + Apple-Mail data-detector rules still ship, just at
    # the top of the body rather than inside <head>. Logged so the gap
    # is visible in CI / verbose runs.
    if "</head>" in inlined:
        inlined = inlined.replace("</head>", style_block + "</head>", 1)
    elif "<body" in inlined:
        # Inject just before <body> (string-find avoids parsing).
        idx = inlined.lower().find("<body")
        inlined = inlined[:idx] + style_block + inlined[idx:]
    else:
        # No <head> and no <body> -- prepend so the rules at least exist.
        log.warning(
            "Rendered HTML had neither </head> nor <body>; kept-style "
            "block prepended at the top of the document."
        )
        inlined = style_block + inlined
    return inlined


__all__ = ["inline"]
