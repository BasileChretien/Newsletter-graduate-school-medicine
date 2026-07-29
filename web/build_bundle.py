"""Package the toolkit's runtime files into the ZIP the web page loads.

The browser build runs the *real* `scripts/` package inside Pyodide --
there is no ported, parallel implementation to drift out of sync. To
do that, Pyodide's virtual filesystem needs the same directory layout
the toolkit expects on disk:

    /repo/scripts/     the pipeline itself
    /repo/templates/   Jinja2 + styles.css
    /repo/locales/     en/ja strings
    /repo/images/      masthead logo + dean photo (brand assets that
                       live outside the DOCX, and that `webapp`
                       mirrors into each build's workdir)

Run this before deploying, and re-run it whenever anything under those
directories changes:

    python web/build_bundle.py

The output (`web/meridian-bundle.zip`) is committed so the page works
from a plain static host with no build step. `verify` mode re-packs to
a temp file and compares, so CI can fail a PR that edits `scripts/`
without refreshing the bundle:

    python web/build_bundle.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_PATH = REPO_ROOT / "web" / "meridian-bundle.zip"

# Directories copied wholesale into the bundle.
INCLUDE_DIRS = ("scripts", "templates", "locales", "images")

# Never ship compiled artefacts, editor leftovers, or -- most
# importantly -- anything that could carry recipient addresses.
EXCLUDE_PARTS = frozenset({"__pycache__", ".pytest_cache", ".git"})
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".pyi")
EXCLUDE_NAMES = frozenset({"recipients.txt", ".DS_Store", "Thumbs.db"})


def _included_files() -> list[Path]:
    """Every file that belongs in the bundle, sorted for determinism."""
    out: list[Path] = []
    for rel in INCLUDE_DIRS:
        base = REPO_ROOT / rel
        if not base.is_dir():
            raise SystemExit(f"Missing directory: {base}")
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if EXCLUDE_PARTS & set(path.parts):
                continue
            if path.suffix in EXCLUDE_SUFFIXES or path.name in EXCLUDE_NAMES:
                continue
            out.append(path)
    return sorted(out)


def write_bundle(target: Path) -> tuple[int, int]:
    """Write the ZIP. Returns (file_count, byte_size).

    Timestamps are pinned so re-running with no source changes produces
    byte-identical output -- that is what makes `--verify` meaningful
    and keeps the committed binary from churning in every diff.
    """
    files = _included_files()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(
                str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    return len(files), target.stat().st_size


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="Fail if the committed bundle is out of date.")
    args = ap.parse_args(argv)

    if args.verify:
        if not BUNDLE_PATH.exists():
            print(f"ERROR: {BUNDLE_PATH.name} is missing. Run "
                  f"`python web/build_bundle.py`.", file=sys.stderr)
            return 1
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "fresh.zip"
            write_bundle(fresh)
            same = (hashlib.sha256(fresh.read_bytes()).hexdigest()
                    == hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest())
        if not same:
            print("ERROR: web/meridian-bundle.zip is out of date with "
                  "scripts/ templates/ locales/ images/. Run "
                  "`python web/build_bundle.py` and commit the result.",
                  file=sys.stderr)
            return 1
        print("web/meridian-bundle.zip is up to date.")
        return 0

    count, size = write_bundle(BUNDLE_PATH)
    print(f"Wrote {BUNDLE_PATH.relative_to(REPO_ROOT)} "
          f"-- {count} files, {size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
