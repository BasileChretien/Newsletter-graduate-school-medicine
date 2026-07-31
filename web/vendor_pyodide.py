"""Fetch the Pyodide runtime so the page can serve it from its own origin.

Why this exists
---------------
The page used to load ~10 MB of executed code from `cdn.jsdelivr.net`.
Two consequences, both demonstrated against the live site:

1. `script-src https://cdn.jsdelivr.net` is an **open-CDN wildcard**.
   jsDelivr serves `/npm/<any-package>` and `/gh/<any-user>/<any-repo>`
   from that same host, so the policy admitted any JavaScript an
   attacker can publish to npm or tag on GitHub. Verified live: an
   arbitrary npm package and an arbitrary GitHub repo both loaded and
   executed on the page.
2. Subresource Integrity covered only the 18.5 KB loader. The loader
   then fetches `pyodide.asm.js`, `pyodide.asm.wasm`,
   `python_stdlib.zip` and `pyodide-lock.json` WITHOUT passing an
   integrity option -- about 0.2% of the executed bytes were checked,
   and the per-package hashes are circular because the lockfile
   carrying them arrives unverified from the same CDN.

Serving from our own origin collapses `script-src` and `connect-src` to
`'self'`, which removes both. It also means the page works on
institutional networks that block public CDNs outright -- a real
consideration for a hospital.

Why fetch instead of committing the files
-----------------------------------------
The runtime is ~8.6 MB against a 5.5 MB repository, and the README
tells editors to download that repository as a ZIP. Committing it would
nearly triple the download for the desktop workflow, which is the
majority path, to benefit the browser one. So the bytes are fetched at
deploy time and checked against `pyodide-assets.json`, which IS
committed and reviewable -- tampering is detectable even though the
payload is not in git history.

Usage
-----
    python web/vendor_pyodide.py                # fetch + verify
    python web/vendor_pyodide.py --write-hashes # after a version bump
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "web" / "pyodide"
HASH_FILE = REPO_ROOT / "web" / "pyodide-assets.json"

# Pinned to the 0.29.x line: `css_inline` -- the Rust-backed CSS inliner
# the whole email layout depends on -- ships in that distribution. The
# 314.x line moved to ABI 2026_0 and has no build for it.
PYODIDE_VERSION = "0.29.4"
PYODIDE_BASE = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"

# The runtime itself.
CORE_FILES = (
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)

# Packages the page loads. Dependencies are resolved from the lockfile,
# so listing the direct ones is enough.
#
# `lxml` is listed explicitly even though nothing here imports it
# directly: it is a dependency of `python-docx`, which is NOT in the
# lockfile, so dependency resolution never reaches it. Leaving it out
# produced a vendor directory that looked complete and then failed at
# `import docx` in the browser.
PACKAGES = ("css-inline", "jinja2", "beautifulsoup4", "pillow", "lxml")

# `python-docx` is the one dependency absent from Pyodide's lockfile, so
# it came from PyPI at every cold load. Vendored here with an explicit
# hash: PyPI permanently reserves filenames, so this exact artifact can
# never be re-uploaded with different bytes.
PYPI_WHEELS = {
    "python_docx-1.2.0-py3-none-any.whl":
        "https://files.pythonhosted.org/packages/py3/p/python-docx/"
        "python_docx-1.2.0-py3-none-any.whl",
}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "meridian-vendor"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve_packages(lock: dict) -> list[str]:
    """Every wheel filename needed for `PACKAGES`, dependencies included."""
    entries = {k.lower(): v for k, v in lock["packages"].items()}
    needed: set[str] = set()
    queue = [p.lower() for p in PACKAGES]
    while queue:
        name = queue.pop()
        entry = entries.get(name)
        if entry is None or name in needed:
            continue
        needed.add(name)
        queue.extend(d.lower() for d in entry.get("depends", []))
    return sorted(entries[n]["file_name"] for n in needed)


def collect() -> dict[str, bytes]:
    """Download everything the page needs. Returns {filename: bytes}."""
    out: dict[str, bytes] = {}
    for name in CORE_FILES:
        out[name] = _fetch(PYODIDE_BASE + name)
        print(f"  fetched {name} ({len(out[name]):,} B)")

    lock = json.loads(out["pyodide-lock.json"])
    for wheel in _resolve_packages(lock):
        out[wheel] = _fetch(PYODIDE_BASE + wheel)
        print(f"  fetched {wheel} ({len(out[wheel]):,} B)")

    for name, url in PYPI_WHEELS.items():
        out[name] = _fetch(url)
        print(f"  fetched {name} ({len(out[name]):,} B)")
    return out


def write_hashes(assets: dict[str, bytes]) -> None:
    payload = {
        "pyodide_version": PYODIDE_VERSION,
        "files": {name: _sha256(data) for name, data in sorted(assets.items())},
    }
    HASH_FILE.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {HASH_FILE.name} with {len(payload['files'])} hashes.")


def verify(assets: dict[str, bytes]) -> list[str]:
    """Compare downloaded bytes against the committed hashes."""
    if not HASH_FILE.exists():
        return [f"{HASH_FILE.name} is missing -- run with --write-hashes"]
    expected = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    if expected.get("pyodide_version") != PYODIDE_VERSION:
        return [f"{HASH_FILE.name} pins Pyodide "
                f"{expected.get('pyodide_version')}, this script wants "
                f"{PYODIDE_VERSION}"]
    problems = []
    want = expected["files"]
    for name in sorted(set(want) | set(assets)):
        if name not in assets:
            problems.append(f"expected but not downloaded: {name}")
        elif name not in want:
            problems.append(f"downloaded but not in the hash file: {name}")
        elif _sha256(assets[name]) != want[name]:
            problems.append(f"HASH MISMATCH: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-hashes", action="store_true",
                    help="Record the downloaded hashes (after a bump).")
    args = ap.parse_args(argv)

    print(f"Fetching Pyodide {PYODIDE_VERSION} ...")
    assets = collect()

    if args.write_hashes:
        write_hashes(assets)
    else:
        problems = verify(assets)
        if problems:
            print("\nERROR: vendored Pyodide does not match the committed "
                  "hashes. Someone changed what the CDN serves, or the "
                  "version was bumped without re-running --write-hashes:",
                  file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"All {len(assets)} files match {HASH_FILE.name}.")

    if VENDOR_DIR.exists():
        shutil.rmtree(VENDOR_DIR)
    VENDOR_DIR.mkdir(parents=True)
    for name, data in assets.items():
        (VENDOR_DIR / name).write_bytes(data)
    total = sum(len(d) for d in assets.values())
    print(f"Wrote {len(assets)} files to web/pyodide/ ({total:,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
