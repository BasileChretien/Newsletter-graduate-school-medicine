"""Inline CSS into HTML using css_inline (Rust-backed, fast)."""

from __future__ import annotations

from pathlib import Path

import css_inline

from scripts.config import TEMPLATES_DIR


def inline(html: str, css_path: Path | None = None) -> str:
    """Return HTML with all stylesheet rules inlined as style attributes."""
    if css_path is None:
        css_path = TEMPLATES_DIR / "styles.css"
    extra_css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    inliner = css_inline.CSSInliner(
        extra_css=extra_css,
        keep_style_tags=False,
        load_remote_stylesheets=False,
    )
    return inliner.inline(html)


__all__ = ["inline"]
