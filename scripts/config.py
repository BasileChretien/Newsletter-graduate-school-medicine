"""Shared constants for the newsletter pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


# Brand palette (mirrors DOCX)
PALETTE = {
    "primary": "#8B1A1F",      # NU wine red
    "accent": "#C9A96E",       # warm gold
    "text": "#1C1C1E",         # near-black charcoal
    "muted": "#6B6B70",        # cool gray
    "cream": "#F7F2EA",        # warm cream tint
    "hairline": "#D9D2C5",     # subtle rule
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


# Default — can be overridden from CLI / env
DEFAULT_REPO = RepoConfig(
    user="BasileChretien",
    repo="Newsletter-graduate-school-medicine",
    branch="main",
)
