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

Where the files come from
-------------------------
Every file has two sources, tried in order: its upstream -- jsDelivr for
the runtime and the lockfile's wheels, PyPI for the wheels vendored from
there -- and a permanent mirror: the assets of this repository's
pre-release `pyodide-runtime-<version>`, published by
`.github/workflows/mirror-runtime.yml`. jsDelivr's `/pyodide/` path
carries no retention promise, and a pinned runtime is kept for years;
without the mirror, a file disappearing upstream would stop every
deploy and freeze the live site. The hash file alone decides which
bytes are acceptable: a source that fails, or serves bytes that do not
match, is skipped.

Usage
-----
    python web/vendor_pyodide.py                # fetch + verify
    python web/vendor_pyodide.py --write-hashes # after a version bump
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "web" / "pyodide"
HASH_FILE = REPO_ROOT / "web" / "pyodide-assets.json"

# Pinned to the 314.x line (ABI `pyemscripten_2026_0`). css-inline -- the
# Rust-backed CSS inliner the whole email layout depends on -- is compiled,
# so the page can only move to a line it publishes a wheel for: 0.21.3 is
# the first release built for 2026_0. Pyodide changes ABI about once a
# year; the weekly update check (tools/check_updates.py) reports when the
# next line has every package the page loads, and tests/test_web_bundle.py
# fails if the compiled wheels do not all match the runtime's ABI.
PYODIDE_VERSION = "314.0.7"
PYODIDE_BASE = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"

# The runtime itself. `web/sw.js` warms the same list (RUNTIME_CORE). Since
# 314.0.0 the loader imports `pyodide.asm.mjs`, an ES module, where it used
# to inject `pyodide.asm.js` as a classic script.
CORE_FILES = (
    "pyodide.js",
    "pyodide.asm.mjs",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)

# Packages the page loads from Pyodide's lockfile. Their dependencies are
# resolved from the lockfile, so listing the direct ones is enough --
# except for the dependencies of wheels loaded BY PATH (PYPI_WHEELS,
# below), whose requirements the resolver never sees:
#
# * `lxml`, for python-docx. Leaving it out produced a vendor directory
#   that looked complete and then failed at `import docx` in the browser.
# * `soupsieve` and `typing-extensions`, for beautifulsoup4 (and
#   typing-extensions for python-docx too).
PACKAGES = ("jinja2", "pillow", "lxml", "soupsieve", "typing-extensions")

# Wheels vendored straight from PyPI, each at exactly the version
# `requirements.txt` pins, so the page and the desktop build render the
# same Word file with the same libraries. tests/test_web_bundle.py keeps
# requirements.txt, this dict and web/app.js in step. PyPI permanently
# reserves filenames, so an exact artifact can never be re-uploaded with
# different bytes.
#
# * `python-docx` and `css-inline` are absent from Pyodide's lockfile.
#   css-inline publishes its own wheel for each ABI instead: `2025_0`
#   (Pyodide 0.29.x) from 0.21.0 on, `2026_0` (314.x) from 0.21.3 on.
# * `beautifulsoup4` is in it, but older (4.14.3) than the desktop pin.
PYPI_WHEELS = {
    "python_docx-1.2.0-py3-none-any.whl":
        "https://files.pythonhosted.org/packages/py3/p/python-docx/"
        "python_docx-1.2.0-py3-none-any.whl",
    "css_inline-0.21.3-cp310-abi3-pyemscripten_2026_0_wasm32.whl":
        "https://files.pythonhosted.org/packages/cp310/c/css-inline/"
        "css_inline-0.21.3-cp310-abi3-pyemscripten_2026_0_wasm32.whl",
    "beautifulsoup4-4.15.0-py3-none-any.whl":
        "https://files.pythonhosted.org/packages/py3/b/beautifulsoup4/"
        "beautifulsoup4-4.15.0-py3-none-any.whl",
}

# The permanent second source for every file ("Where the files come from",
# above). A fork points this at its own copy with MERIDIAN_RUNTIME_MIRROR.
MIRROR_REPOSITORY = "BasileChretien/Newsletter-graduate-school-medicine"


def mirror_base() -> str:
    """Base URL of the mirror for the pinned runtime, ending in `/`."""
    base = (os.environ.get("MERIDIAN_RUNTIME_MIRROR")
            or f"https://github.com/{MIRROR_REPOSITORY}/releases/download/"
               f"pyodide-runtime-{PYODIDE_VERSION}/")
    return base if base.endswith("/") else base + "/"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "meridian-vendor"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_verified(name: str, urls: list[str], expected: str | None) -> bytes:
    """The first bytes for `name` that a source serves and the hash accepts.

    `expected` is the file's committed SHA-256. Without one -- a
    `--write-hashes` run after a version bump -- the first source that
    answers wins. A source that fails, or serves bytes that do not match,
    is skipped rather than fatal: that is precisely the case the mirror is
    for. Only when no source yields acceptable bytes does this raise, and
    the error names every attempt.
    """
    attempts = []
    for url in urls:
        try:
            data = _fetch(url)
        except Exception as exc:  # noqa: BLE001 -- any failure: try the next source
            attempts.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        if expected is None or _sha256(data) == expected:
            return data
        attempts.append(f"{url}: served bytes that do not match the committed hash")
    raise RuntimeError(f"could not fetch {name}:\n    " + "\n    ".join(attempts))


_SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")


def _safe_name(name: str) -> str:
    """Reject a filename that could escape `web/pyodide/`.

    These names come out of `pyodide-lock.json`, which is fetched from
    the CDN and is NOT yet hash-verified at the point they are used --
    verification needs the full set, and the set is defined by this very
    file. They then reach both a URL (`PYODIDE_BASE + name`) and a write
    path (`VENDOR_DIR / name`).

    In the deploy path a tampered name fails closed already, because a
    file absent from `pyodide-assets.json` trips the "downloaded but not
    in the hash file" check before anything is written. But
    `--write-hashes` has no such backstop -- it trusts what it
    downloads by definition -- so `"../../.github/workflows/x.yml"`
    would be written outside the vendor directory on a maintainer's own
    machine. Cheap to close, so closed.
    """
    if not _SAFE_FILENAME.match(name) or Path(name).name != name:
        raise ValueError(
            f"refusing a filename from the lockfile that is not a plain "
            f"basename: {name!r}")
    return name


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
    return sorted(_safe_name(entries[n]["file_name"]) for n in needed)


def collect(expected: dict[str, str] | None = None) -> dict[str, bytes]:
    """Download everything the page needs. Returns {filename: bytes}.

    `expected` maps filenames to their committed hashes. A file it does not
    list -- or everything, with `None` -- comes from the first source that
    answers; `verify` then reports anything unexpected.
    """
    expected = expected or {}
    mirror = mirror_base()
    out: dict[str, bytes] = {}

    def get(name: str, upstream: str) -> None:
        out[name] = fetch_verified(name, [upstream, mirror + name],
                                   expected.get(name))
        print(f"  fetched {name} ({len(out[name]):,} B)")

    for name in CORE_FILES:
        get(name, PYODIDE_BASE + name)

    lock = json.loads(out["pyodide-lock.json"])
    for wheel in _resolve_packages(lock):
        get(wheel, PYODIDE_BASE + wheel)

    for name, url in PYPI_WHEELS.items():
        get(name, url)
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


def _recorded_hashes() -> dict[str, str] | None:
    """The committed hashes for the pinned version, if there are any."""
    if not HASH_FILE.exists():
        return None
    recorded = json.loads(HASH_FILE.read_text(encoding="utf-8"))
    if recorded.get("pyodide_version") != PYODIDE_VERSION:
        return None
    return recorded.get("files", {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-hashes", action="store_true",
                    help="Record the downloaded hashes (after a bump).")
    args = ap.parse_args(argv)

    print(f"Fetching Pyodide {PYODIDE_VERSION} ...")
    try:
        assets = collect(None if args.write_hashes else _recorded_hashes())
    except RuntimeError as exc:
        print(f"\nERROR: {exc}\nNeither the upstream source nor the mirror "
              f"({mirror_base()}) served these bytes.", file=sys.stderr)
        return 1

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
        (VENDOR_DIR / _safe_name(name)).write_bytes(data)
    total = sum(len(d) for d in assets.values())
    print(f"Wrote {len(assets)} files to web/pyodide/ ({total:,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
