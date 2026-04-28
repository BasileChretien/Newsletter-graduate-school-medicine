"""Shared pytest fixtures.

The toolkit caches a few expensive resolver results at import time
(`get_default_repo`, `load_locale`). Tests that change env vars after
the cache has been primed would otherwise see stale values.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_module_caches() -> None:
    """Invalidate functools / lru caches before AND after every test."""
    from scripts.config import get_default_repo
    from scripts.i18n import load_locale

    for fn in (get_default_repo, load_locale):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
    yield
    for fn in (get_default_repo, load_locale):
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()
