"""Inline CSS into HTML using css_inline (Rust-backed, fast).

After inlining, a small kept-as-<style> block carries rules that MUST
NOT be inlined -- @media queries (print, prefers-color-scheme), pseudo
states (Apple Mail x-apple-data-detectors), and a forced-colors safety
net for Outlook Windows high-contrast mode.
"""

from __future__ import annotations

from pathlib import Path

import css_inline

from scripts.config import TEMPLATES_DIR


# Rules that survive the css_inline pass by being injected into <head>
# AFTER inlining. Email clients that strip <style> blocks (notably
# Gmail's classic webmail) lose these silently -- that's acceptable for
# print and forced-colors, both of which degrade gracefully.
_KEPT_STYLES = """
@media print {
  body, .container { background: #ffffff !important; }
  .footer { background: #ffffff !important; color: #1C1C1E !important; }
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
    # Inject the kept-style block right before </head>.
    style_block = f"<style type=\"text/css\">{_KEPT_STYLES}</style>"
    if "</head>" in inlined:
        inlined = inlined.replace("</head>", style_block + "</head>", 1)
    return inlined


__all__ = ["inline"]
