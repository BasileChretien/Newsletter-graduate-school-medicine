"""Tiny locale loader.

Reads `locales/<code>.toml` (UTF-8) into a nested dict and exposes a
`t(key, default=...)` lookup. Supports dotted paths so callers can do
`t("errors.no_python")`. Falls back to English on missing keys.

Locale resolution priority:
  1. explicit argument to `load_locale(code)`
  2. env var MERIDIAN_LOCALE
  3. system locale (locale.getlocale)
  4. "en"
"""

from __future__ import annotations

import locale as _locale
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:                              # pragma: no cover
    import tomli as tomllib                       # type: ignore

from scripts.config import PROJECT_ROOT

log = logging.getLogger(__name__)

LOCALES_DIR = PROJECT_ROOT / "locales"
_DEFAULT_LOCALE = "en"
_SUPPORTED = ("en", "ja")


def _detect_locale() -> str:
    code = os.environ.get("MERIDIAN_LOCALE", "").strip().lower()
    if code:
        return code.split("_")[0]
    try:
        sys_locale, _enc = _locale.getlocale()
    except Exception:
        sys_locale = None
    if sys_locale:
        sys_locale = sys_locale.lower()
        if sys_locale.startswith("ja"):
            return "ja"
    return _DEFAULT_LOCALE


@lru_cache(maxsize=8)
def load_locale(code: str | None = None) -> dict[str, Any]:
    """Load `locales/<code>.toml` (with English fallback)."""
    code = (code or _detect_locale() or _DEFAULT_LOCALE).lower().split("_")[0]
    if code not in _SUPPORTED:
        code = _DEFAULT_LOCALE

    en_path = LOCALES_DIR / f"{_DEFAULT_LOCALE}.toml"
    en_data: dict[str, Any] = {}
    if en_path.exists():
        with en_path.open("rb") as fh:
            en_data = tomllib.load(fh)

    if code == _DEFAULT_LOCALE:
        return en_data

    target = LOCALES_DIR / f"{code}.toml"
    if not target.exists():
        log.debug("Locale %s not found -- falling back to English.", code)
        return en_data

    with target.open("rb") as fh:
        target_data = tomllib.load(fh)

    return _merge(en_data, target_data)


def _merge(base: dict, overlay: dict) -> dict:
    """Deep-merge `overlay` over `base`, preferring overlay leaf values."""
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def t(key: str, *, default: str | None = None,
      locale: str | None = None) -> str:
    """Look up a dotted key in the loaded locale; return default on miss."""
    data: Any = load_locale(locale)
    for part in key.split("."):
        if not isinstance(data, dict) or part not in data:
            return default if default is not None else key
        data = data[part]
    return str(data) if data is not None else (default or key)


__all__ = ["load_locale", "t", "LOCALES_DIR"]
