"""Shared constants for the newsletter pipeline."""

from __future__ import annotations

import functools
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Filesystem layout
ORIGINAL_TEMPLATE = PROJECT_ROOT / "NagoyaU_MedSchool_Newsletter_Template-2.docx"
MERIDIAN_TEMPLATE = PROJECT_ROOT / "Meridian_Newsletter_Template.docx"
ASSETS_DIR = PROJECT_ROOT / "assets"
DROP_DIR = PROJECT_ROOT / "drop-images"
DIST_DIR = PROJECT_ROOT / "dist"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
IMAGES_DIR = PROJECT_ROOT / "images"

# Permanent brand assets (committed at the repo root, served via raw URLs)
LOGO_FILENAME = "Nagoya_University_Graduate_school_medicine_logo.jpg"
LOGO_PATH = IMAGES_DIR / LOGO_FILENAME
LOGO_REL = f"images/{LOGO_FILENAME}"

DEAN_FILENAME = "Nagoya_university_school_medicine_dean.jpg"
DEAN_PATH = IMAGES_DIR / DEAN_FILENAME
DEAN_REL = f"images/{DEAN_FILENAME}"

# Placeholder text in the DOCX Dean cell that should be replaced by the photo.
DEAN_PHOTO_PLACEHOLDER = "[ Photo ]"

# Current dean — used to replace the [Dean's Name] / [Full Name] placeholders
# in the Dean section so the editor doesn't have to type it every issue.
DEAN_NAME = "Prof. Masahisa Katsuno"
DEAN_NAME_PLAIN = "Masahisa Katsuno"      # signature form, with ", MD, PhD" appended
DEAN_TITLE = "Dean, Graduate School of Medicine, Nagoya University"


# Sub-section headings within the 7 main sections. Keep in sync with the
# template's text (these strings drive both the docx restyle and the parser
# block detection -- one place to edit, two consumers).
SUBHEAD_TEXTS: frozenset[str] = frozenset({
    "Notable Publications", "Grants & Funding Awarded",
    "New Programs / Curriculum Updates", "New Partnerships & MOUs",
    "Visiting Scholars & Exchange", "Student Awards & Honors",
    "Thesis Defenses & Graduations", "Student Club & Community Activities",
    "New Faculty & Staff Welcome", "Deadlines & Notices",
})


# Brand palette per the Nagoya University official design guideline
# (https://www.med.nagoya-u.ac.jp/intranet/pr/logo/).
PALETTE = {
    "primary": "#003F88",      # NU blue (deep navy, official primary)
    "primary_soft": "#1A5BA8", # lighter shade for hover / inverse contexts
    "accent": "#C9A96E",       # warm gold (decorative use only)
    "accent_aa": "#A8864B",    # darker gold for text/markers (WCAG AA on white)
    "text": "#1C1C1E",         # near-black charcoal
    "muted": "#6B6B70",        # cool gray
    "cream": "#EEF2F7",        # cool off-white tint (masthead) -- harmonises with blue
    "zebra": "#DCE3EE",        # cooler stripe for data tables
    "hairline": "#C9D2DE",     # subtle rule
    "white": "#FFFFFF",
}


# Newsletter masthead
TITLE = "MERIDIAN"
TAGLINE = "Where medicine meets the world."
SUBTITLE = "Newsletter of the Graduate School of Medicine – Nagoya University"


# Email constraints
GMAIL_CLIP_BYTES = 102_400  # Gmail clips messages > 102KB


@dataclass(frozen=True)
class RepoConfig:
    """GitHub repo coordinates used to build raw image URLs."""

    user: str
    repo: str
    branch: str = "main"

    def raw_url(self, relative_path: str) -> str:
        rel = relative_path.lstrip("/").replace("\\", "/")
        return (
            f"https://raw.githubusercontent.com/"
            f"{self.user}/{self.repo}/{self.branch}/{rel}"
        )


# Fallback if neither env vars nor `git remote` reveal the repo.
_FALLBACK_REPO = RepoConfig(
    user="BasileChretien",
    repo="Newsletter-graduate-school-medicine",
    branch="main",
)


# Match GitHub HTTPS, SSH (git@github.com:user/repo) and ssh:// forms.
# Allows dots in repo names (e.g. `meridian.newsletter`).
_GIT_REMOTE_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<user>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def _read_git_origin(cwd: Path) -> str:
    """Return `git remote get-url origin` stdout, or '' on any failure.

    Narrow exception handling so a real bug in subprocess wiring
    doesn't get masked by the broad `except Exception` of the past.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(cwd), capture_output=True, text=True,
            timeout=5, check=False,
        )
        return (result.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.SubprocessError, OSError) as e:
        log.debug("Could not read git origin: %s", e)
        return ""


@functools.cache
def get_default_repo() -> RepoConfig:
    """Resolve the GitHub repo coordinates used to build raw image URLs.

    Resolution order:
      1. Env vars MERIDIAN_REPO_USER / MERIDIAN_REPO_NAME / MERIDIAN_REPO_BRANCH
      2. `git remote get-url origin` (HTTPS / SSH / ssh:// all accepted)
      3. Hard-coded fallback (project's original home)

    Lazy + cached: not called at import time. Avoids a 5-second
    blocking subprocess on every test collection / module reload.
    """
    env_user = os.environ.get("MERIDIAN_REPO_USER")
    env_repo = os.environ.get("MERIDIAN_REPO_NAME")
    env_branch = os.environ.get("MERIDIAN_REPO_BRANCH")
    if env_user and env_repo:
        return RepoConfig(
            user=env_user, repo=env_repo, branch=env_branch or "main",
        )

    url = _read_git_origin(PROJECT_ROOT)
    m = _GIT_REMOTE_RE.match(url) if url else None
    if m:
        return RepoConfig(
            user=m.group("user"),
            repo=m.group("repo"),
            branch=env_branch or "main",
        )
    return _FALLBACK_REPO


def __getattr__(name: str):
    """Lazy attribute lookup so legacy `from scripts.config import DEFAULT_REPO`
    still works, but the `git remote` call only fires on first access."""
    if name == "DEFAULT_REPO":
        return get_default_repo()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
