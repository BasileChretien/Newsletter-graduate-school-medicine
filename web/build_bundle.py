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

# Text files are normalized to LF before packing. Without this the
# bundle's bytes depend on the *checkout*, not the source: with
# `core.autocrlf=true` a Windows working tree holds CRLF and a Linux
# one holds LF, so the committed zip built on one platform can never
# match a rebuild on the other -- and `--verify` (which CI runs on all
# three) would fail for a reason that has nothing to do with anyone's
# changes. Python, Jinja2 and TOML are all newline-agnostic, so LF
# inside the bundle is purely a determinism device.
TEXT_SUFFIXES = frozenset({
    ".py", ".j2", ".css", ".toml", ".html", ".txt", ".json", ".md",
})


def _archive_name(path: Path) -> str:
    """Path as it appears inside the zip -- always POSIX-separated."""
    return path.relative_to(REPO_ROOT).as_posix()


def _included_files() -> list[Path]:
    """Every file that belongs in the bundle, sorted for determinism.

    Sorted by the POSIX archive name rather than by `Path`: `Path`
    ordering uses a case-folded, backslash-separated key on Windows and
    a case-sensitive, slash-separated one elsewhere, so the same tree
    could be packed in two different orders.
    """
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
    return sorted(out, key=_archive_name)


def _payload(path: Path) -> bytes:
    """File bytes, with text normalized to LF. See `TEXT_SUFFIXES`."""
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        return data.replace(b"\r\n", b"\n")
    return data


def write_bundle(target: Path) -> tuple[int, int]:
    """Write the ZIP. Returns (file_count, byte_size).

    Timestamps are pinned and text is LF-normalized so re-running with
    no source changes produces byte-identical output on any platform --
    that is what makes `--verify` meaningful and keeps the committed
    binary from churning in every diff.
    """
    files = _included_files()
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(
                _archive_name(path),
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            # `ZipInfo` defaults this to 0 (MS-DOS) on Windows and 3
            # (Unix) on everything else, and it is written into the
            # header -- so identical content produced two different
            # files depending on who ran the script. Pinned to Unix.
            info.create_system = 3
            z.writestr(info, _payload(path))
    return len(files), target.stat().st_size


def bundle_drift() -> list[str]:
    """Describe how the committed bundle differs from the sources.

    Compares CONTENT (name -> sha256 of the packed payload), not the
    zip's bytes. A byte comparison also catches differences in the
    container itself -- `create_system`, compression-level tweaks
    between Python versions, field ordering -- none of which mean the
    browser would run stale code, but all of which would fail CI on a
    machine that differs from whoever last ran the builder. This
    compares the thing we actually care about, and names the files that
    drifted so the failure is actionable.

    Returns an empty list when the bundle is current.
    """
    def _sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    expected = {_archive_name(p): _sha(_payload(p)) for p in _included_files()}
    with zipfile.ZipFile(BUNDLE_PATH) as z:
        actual = {name: _sha(z.read(name)) for name in z.namelist()}

    drift: list[str] = []
    for name in sorted(set(expected) - set(actual)):
        drift.append(f"missing from the bundle: {name}")
    for name in sorted(set(actual) - set(expected)):
        drift.append(f"no longer in the sources: {name}")
    for name in sorted(set(expected) & set(actual)):
        if expected[name] != actual[name]:
            drift.append(f"changed since the bundle was built: {name}")
    return drift


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
        drift = bundle_drift()
        if drift:
            print("ERROR: web/meridian-bundle.zip is out of date with "
                  "scripts/ templates/ locales/ images/:", file=sys.stderr)
            for line in drift:
                print(f"  {line}", file=sys.stderr)
            print("Run `python web/build_bundle.py` and commit the result.",
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
