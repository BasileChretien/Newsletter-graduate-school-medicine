"""Shared pytest fixtures.

The toolkit caches a few expensive resolver results at import time
(`get_default_repo`, `load_locale`). Tests that change env vars after
the cache has been primed would otherwise see stale values.

The fixture below auto-discovers every `functools.cache` /
`functools.lru_cache` decorated callable across `scripts/*` modules
and clears it before AND after each test -- so adding a NEW cached
function in any future module is automatically covered without the
fixture needing to be edited.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

import pytest

import scripts


def _iter_cached_callables() -> Iterable[object]:
    """Yield every callable in scripts.* that exposes `cache_clear`."""
    seen: set[int] = set()
    # Walk submodules under `scripts.` (one level deep is enough for
    # the toolkit; `scripts.mail.*` is also picked up by walk_packages).
    for mod_info in pkgutil.walk_packages(
        scripts.__path__, prefix=scripts.__name__ + ".",
    ):
        try:
            module = importlib.import_module(mod_info.name)
        except Exception:
            continue
        for name in dir(module):
            obj = getattr(module, name, None)
            if callable(obj) and hasattr(obj, "cache_clear"):
                if id(obj) in seen:
                    continue
                seen.add(id(obj))
                yield obj


@pytest.fixture(autouse=True)
def _clear_module_caches() -> Iterable[None]:
    """Invalidate every functools-cached callable before AND after each test."""
    for fn in _iter_cached_callables():
        fn.cache_clear()
    yield
    for fn in _iter_cached_callables():
        fn.cache_clear()
