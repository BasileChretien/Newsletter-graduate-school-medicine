"""Stub for scripts/config.py so pyright sees the module-level
__getattr__-resolved attributes (DEFAULT_REPO) as real symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT: Path
ORIGINAL_TEMPLATE: Path
MERIDIAN_TEMPLATE: Path
ASSETS_DIR: Path
DROP_DIR: Path
DIST_DIR: Path
TEMPLATES_DIR: Path
IMAGES_DIR: Path

LOGO_FILENAME: str
LOGO_PATH: Path
LOGO_REL: str

DEAN_FILENAME: str
DEAN_PATH: Path
DEAN_REL: str
DEAN_PHOTO_PLACEHOLDER: str
DEAN_NAME: str
DEAN_NAME_PLAIN: str
DEAN_TITLE: str

PALETTE: dict[str, str]
SUBHEAD_TEXTS: frozenset[str]
TITLE: str
TAGLINE: str
SUBTITLE: str
GMAIL_CLIP_BYTES: int


@dataclass(frozen=True)
class RepoConfig:
    user: str
    repo: str
    branch: str = ...

    def raw_url(self, relative_path: str) -> str: ...


def get_default_repo() -> RepoConfig: ...

# Resolved lazily via module __getattr__ on first access. Declared here
# so pyright / mypy see it as a real attribute of the module.
DEFAULT_REPO: RepoConfig
