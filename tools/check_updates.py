"""Weekly dependency and runtime check for MERIDIAN.

Dependabot bumps `requirements*.txt` and the workflow actions by pull
request. This covers what it cannot see, and runs every Monday from
`.github/workflows/update-check.yml`, which keeps one GitHub issue current:

  * Pyodide -- the runtime the browser build is pinned to in
    `web/vendor_pyodide.py`, and whether a newer release still ships every
    package the page loads (`css-inline` above all: the whole email
    layout depends on it);
  * browser build vs desktop -- the wheel versions recorded in
    `web/pyodide-assets.json` against `requirements.txt`, because the two
    builds must render the same Word file the same way;
  * wheels vendored straight from PyPI (`python-docx`);
  * Python -- the `requires-python` floor and the versions the test
    matrix runs, against their end-of-life dates.

Standard library only, so the workflow needs no `pip install`. It never
crashes on bad input: anything unexpected becomes a finding in the
report, because a crashed run leaves the tracking issue silently stale.

Usage:
    python tools/check_updates.py [--report update-report.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

PYODIDE_RELEASES_URL = (
    "https://api.github.com/repos/pyodide/pyodide/releases?per_page=30")
PYODIDE_LOCK_URL = (
    "https://cdn.jsdelivr.net/pyodide/v{version}/full/pyodide-lock.json")
PYPI_URL = "https://pypi.org/pypi/{name}/json"
PYTHON_EOL_URL = "https://endoflife.date/api/python.json"

# The workflow whose matrix IS the set of supported Python versions. Other
# workflows pin a Python for their own tooling (deploy-web, update-check);
# those say nothing about what editors can run.
TEST_WORKFLOW = Path(".github") / "workflows" / "tests.yml"

# How far ahead an end-of-life date turns into a warning: enough time to
# raise `requires-python` and re-test within an ordinary release cycle.
EOL_WARNING_DAYS = 120

# Most urgent first. "action" and "warning" keep the tracking issue open;
# "info" is reported but does not, so a blocked upgrade that nobody can
# act on does not hold the issue open by itself.
LEVELS = ("action", "warning", "info", "ok")
_HEADINGS = {
    "action": "Needs action",
    "warning": "Warnings",
    "info": "For information",
    "ok": "Up to date",
}


@dataclass(frozen=True)
class Finding:
    check: str
    level: str
    title: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(f"unknown level {self.level!r}; use one of {LEVELS}")


@dataclass(frozen=True)
class VendorPins:
    pyodide: str
    packages: tuple[str, ...]
    pypi_wheels: dict[str, str]
    # Name -> wheel filename. The filename carries the Pyodide ABI of a
    # compiled wheel (css-inline), which decides what the page can load.
    pypi_wheel_files: dict[str, str] = field(default_factory=dict)


# ---------- network ----------
def fetch_json(url: str):
    """GET `url` and decode it as JSON.

    A `GITHUB_TOKEN`, when set, lifts the API's anonymous rate limit. It
    is sent to api.github.com and nowhere else.
    """
    headers = {"User-Agent": "meridian-update-check",
               "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _unexpected(what: str, payload: object) -> str:
    """A short, safe description of a payload that had the wrong shape."""
    return f"Expected a list from {what}, got {type(payload).__name__}: {str(payload)[:200]}"


# ---------- parsing ----------
_FINAL_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)")


def parse_version(text: str) -> tuple[int, ...] | None:
    """A final release as a tuple of integers; None for anything else.

    Pre-releases (`315.0.0a2`, `6.1.0rc1`, `1.0.dev3`) return None, so
    they are never offered as an upgrade.
    """
    match = _FINAL_VERSION.fullmatch((text or "").strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _key(version: tuple[int, ...]) -> tuple[int, ...]:
    """Comparable form: `1.2` and `1.2.0` are the same release."""
    parts = list(version)
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def normalise(name: str) -> str:
    """PEP 503 project name: lower case, runs of `-_.` become one hyphen."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _wheel_name_version(filename: str) -> tuple[str, str] | None:
    """`css_inline-0.16.0-cp39-abi3-...whl` -> ("css-inline", "0.16.0")."""
    if not filename.endswith(".whl"):
        return None
    parts = filename[:-len(".whl")].split("-")
    if len(parts) < 3:
        return None
    return normalise(parts[0]), parts[1]


def _platform_tag(filename: str) -> str | None:
    """A compiled wheel's platform tag (`pyemscripten_2025_0_wasm32`);
    None for a pure-Python wheel, or for anything that is not a wheel."""
    if not filename.endswith(".whl") or filename.endswith("-none-any.whl"):
        return None
    return filename[:-len(".whl")].rsplit("-", 1)[-1]


def _pypi_has_build_for_abi(fetch_json: Callable[[str], object], name: str,
                            abi: str) -> bool:
    """Whether any release of `name` on PyPI ships a wheel for Pyodide `abi`."""
    try:
        releases = fetch_json(PYPI_URL.format(name=name)).get("releases", {})
        return any(
            isinstance(entry, dict)
            and f"_{abi}_wasm32" in str(entry.get("filename", ""))
            for files in releases.values() if isinstance(files, list)
            for entry in files)
    except Exception:  # noqa: BLE001 -- unknown counts as not published
        return False


def read_vendor_pins(source: str) -> VendorPins:
    """The runtime pins declared in `web/vendor_pyodide.py`.

    Read as text rather than imported: importing that script would pull
    in its download code. A reshaped file raises here, and `main` turns
    that into an "action" finding, so the issue says the check broke.
    """
    version = re.search(r'^PYODIDE_VERSION\s*=\s*"([^"]+)"', source, re.M)
    packages = re.search(r"^PACKAGES\s*=\s*\((.*?)\)", source, re.M | re.S)
    wheels = re.search(r"^PYPI_WHEELS\s*=\s*\{(.*?)^\}", source, re.M | re.S)
    if not (version and packages and wheels):
        raise ValueError(
            "web/vendor_pyodide.py no longer declares PYODIDE_VERSION, "
            "PACKAGES and PYPI_WHEELS in the form tools/check_updates.py reads")
    pypi, files = {}, {}
    for filename in re.findall(r'"([^"/]+\.whl)"\s*:', wheels.group(1)):
        parsed = _wheel_name_version(filename)
        if parsed:
            pypi[parsed[0]] = parsed[1]
            files[parsed[0]] = filename
    return VendorPins(
        pyodide=version.group(1),
        packages=tuple(re.findall(r'"([^"]+)"', packages.group(1))),
        pypi_wheels=pypi,
        pypi_wheel_files=files,
    )


def browser_versions(assets: dict) -> dict[str, str]:
    """Package versions the browser build ships, from its hash file."""
    versions = {}
    for filename in assets.get("files", {}):
        parsed = _wheel_name_version(filename)
        if parsed:
            versions[parsed[0]] = parsed[1]
    return versions


_REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(===|==|~=|>=|<=|!=|>|<)\s*([^\s;,#]+)")


def desktop_requirements(text: str) -> dict[str, tuple[str, str]]:
    """`requirements.txt` as {normalised name: (operator, version)}."""
    requirements = {}
    for line in text.splitlines():
        match = _REQUIREMENT.match(line.split("#", 1)[0])
        if match:
            requirements[normalise(match.group(1))] = (match.group(2), match.group(3))
    return requirements


def python_floor(pyproject: str) -> str | None:
    """The `X.Y` in `requires-python = ">=X.Y"` (either TOML quote style)."""
    match = re.search(
        r"""^requires-python\s*=\s*["']\s*>=\s*([0-9.]+)""", pyproject, re.M)
    return match.group(1) if match else None


def ci_python_versions(workflows: Iterable[str]) -> list[str]:
    """Every literal `python-version` in the given workflow texts."""
    found: set[str] = set()
    for text in workflows:
        for match in re.finditer(r"python-version:\s*(.+)", text):
            found.update(re.findall(r"\d+\.\d+", match.group(1)))
    return sorted(found, key=lambda v: parse_version(v) or ())


# ---------- checks ----------
def check_browser_parity(browser: dict[str, str],
                         desktop: dict[str, tuple[str, str]]) -> list[Finding]:
    """The browser build's packages against the desktop requirements."""
    findings = []
    for name in sorted(set(browser) & set(desktop)):
        operator, wanted = desktop[name]
        have = browser[name]
        have_v, wanted_v = parse_version(have), parse_version(wanted)
        # `1.2` and `1.2.0` are one release; fall back to the text only when
        # either side is not a plain release number.
        same = (_key(have_v) == _key(wanted_v)) if (have_v and wanted_v) else have == wanted
        if operator == "==" and not same:
            findings.append(Finding(
                "parity", "warning",
                f"{name}: the browser build runs {have}, the desktop pins {wanted}",
                "The two builds can render the same Word file differently. "
                "Align them, or record why they differ."))
        elif operator == ">=" and have_v and wanted_v and _key(have_v) < _key(wanted_v):
            findings.append(Finding(
                "parity", "warning",
                f"{name}: the browser build runs {have}, below the desktop floor >={wanted}",
                "Floors in requirements.txt carry fixes (several are security "
                "fixes); the browser build ships the version before one. It "
                "comes from the Pyodide lockfile, so it moves with a Pyodide "
                "upgrade."))
        else:
            findings.append(Finding(
                "parity", "ok", f"{name}: browser {have}, desktop {operator}{wanted}"))
    return findings


def _line(version: tuple[int, ...]) -> tuple[int, ...]:
    """Pyodide's compatibility line: `0.29` before the 314 scheme, then `314`."""
    return version[:2] if version[0] == 0 else version[:1]


def check_pyodide(pinned: str, packages: Iterable[str], releases: object,
                  fetch_lock: Callable[[str], dict],
                  native_wheels: dict[str, str] | None = None,
                  fetch_json: Callable[[str], object] | None = None,
                  ) -> list[Finding]:
    """Is there a newer Pyodide, and could the page run on it?

    Moving to a newer compatibility line needs every lockfile package the
    page loads AND, for the new line's ABI, a build of every compiled wheel
    it vendors from PyPI (`native_wheels`: css-inline). Pyodide's own
    lockfile can have everything and still not run the page.
    """
    if not isinstance(releases, list):
        # GitHub answers a rate limit or an outage with an error OBJECT.
        return [Finding("pyodide", "warning",
                        "Pyodide's release list came back in an unexpected shape",
                        _unexpected("the GitHub releases API", releases))]
    pinned_v = parse_version(pinned)
    if pinned_v is None:
        return [Finding("pyodide", "warning",
                        f"The Pyodide pin {pinned} is not a release version")]
    finals = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "").lstrip("v")
        version = parse_version(tag)
        if version:
            finals.append((_key(version), version, tag))
    newer = sorted(f for f in finals if f[0] > _key(pinned_v))
    if not newer:
        return [Finding("pyodide", "ok", f"Pyodide {pinned} is the newest release")]

    findings = []
    line = _line(pinned_v)
    same_line = [f for f in newer if _line(f[1]) == line]
    if same_line:
        tag = same_line[-1][2]
        findings.append(Finding(
            "pyodide", "action",
            f"Pyodide {tag} is out on the pinned {'.'.join(map(str, line))} line "
            f"(pinned: {pinned})",
            "Same compatibility line, so every package keeps its build. Set "
            "PYODIDE_VERSION in web/vendor_pyodide.py, run "
            "`python web/vendor_pyodide.py --write-hashes`, and commit "
            "web/pyodide-assets.json."))

    other_line = [f for f in newer if _line(f[1]) != line]
    if other_line:
        tag = other_line[-1][2]
        try:
            lock = fetch_lock(tag)
            available = {normalise(name) for name in lock.get("packages", {})}
        except Exception as exc:  # noqa: BLE001 -- report it, never crash the run
            findings.append(Finding(
                "pyodide", "warning",
                f"Pyodide {tag} is out, but its package list could not be checked",
                _describe(exc)))
        else:
            missing = [p for p in packages if normalise(p) not in available]
            info = lock.get("info")
            abi = info.get("abi_version") if isinstance(info, dict) else None
            for name, filename in sorted((native_wheels or {}).items()):
                if _platform_tag(filename) is None:
                    continue
                if not (abi and fetch_json
                        and _pypi_has_build_for_abi(fetch_json, name, abi)):
                    missing.append(
                        f"{name} (no wheel for ABI {abi or 'unknown'} on PyPI)")
            if missing:
                findings.append(Finding(
                    "pyodide", "info",
                    f"Pyodide {tag} is out, but the page cannot run on it yet",
                    f"Missing from its package list: {', '.join(missing)}. "
                    f"Stay on {pinned} until they are published for it."))
            else:
                findings.append(Finding(
                    "pyodide", "action",
                    f"Pyodide {tag} has every package the page loads (pinned: {pinned})",
                    "This crosses a compatibility line: bump PYODIDE_VERSION, "
                    "switch the vendored compiled wheels (css-inline) to their "
                    "builds for the new ABI, relax the 0.29.x pin in "
                    "tests/test_web_bundle.py, run `python web/vendor_pyodide.py "
                    "--write-hashes`, and let the web-engine workflow compare "
                    "the result with the desktop build before merging."))
    return findings


def check_pypi_wheels(pinned: dict[str, str],
                      fetch_json: Callable[[str], object],
                      files: dict[str, str] | None = None) -> list[Finding]:
    """Wheels vendored straight from PyPI, against PyPI's latest release.

    A compiled wheel (css-inline) can only move to a release that ships a
    build for the page's Pyodide ABI, so a newer release without one is
    reported for information rather than offered as an upgrade.
    """
    files = files or {}
    findings = []
    for name, have in sorted(pinned.items()):
        try:
            data = fetch_json(PYPI_URL.format(name=name))
            latest = str(data["info"]["version"])
        except Exception as exc:  # noqa: BLE001 -- report it, never crash the run
            findings.append(Finding(
                "pypi", "warning", f"{name}: PyPI could not be checked",
                _describe(exc)))
            continue
        have_v, latest_v = parse_version(have), parse_version(latest)
        if not (have_v and latest_v and _key(latest_v) > _key(have_v)):
            findings.append(Finding(
                "pypi", "ok", f"{name} {have} is the newest release on PyPI"))
            continue
        platform = _platform_tag(files.get(name, ""))
        if platform:
            latest_files = data.get("urls") if isinstance(data, dict) else None
            built = isinstance(latest_files, list) and any(
                isinstance(entry, dict)
                and str(entry.get("filename", "")).endswith(f"-{platform}.whl")
                for entry in latest_files)
            if not built:
                findings.append(Finding(
                    "pypi", "info",
                    f"{name} {latest} is on PyPI, but without a {platform} "
                    f"build; the browser build keeps {have}",
                    "The page can only load a wheel built for its Pyodide ABI, "
                    "so there is nothing to do until one is published."))
                continue
        findings.append(Finding(
            "pypi", "action",
            f"{name} {latest} is on PyPI; the browser build vendors {have}",
            "Bump it in requirements.txt, in PY_PACKAGES in web/app.js and in "
            "PYPI_WHEELS in web/vendor_pyodide.py, then run "
            "`python web/vendor_pyodide.py --write-hashes`. "
            "tests/test_web_bundle.py keeps the three in step."))
    return findings


def _iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def check_python(floor: str | None, ci_versions: Iterable[str],
                 eol_data: object, today: date) -> list[Finding]:
    """The Python versions MERIDIAN supports, against their end of life."""
    if not isinstance(eol_data, list):
        return [Finding("python", "warning",
                        "Python's end-of-life data came back in an unexpected shape",
                        _unexpected("endoflife.date", eol_data))]
    entries = [entry for entry in eol_data if isinstance(entry, dict)]
    ci_versions = list(ci_versions)
    cycles = {str(entry.get("cycle")): entry for entry in entries}
    roles: dict[str, list[str]] = {}
    if floor:
        roles.setdefault(floor, []).append("the requires-python floor")
    for version in ci_versions:
        roles.setdefault(version, []).append("the version CI tests")

    findings = []
    for version, what in roles.items():
        label = f"Python {version} ({' and '.join(what)})"
        entry = cycles.get(version)
        if entry is None:
            findings.append(Finding("python", "warning",
                                    f"{label}: no end-of-life data found"))
            continue
        end = _iso_date(entry.get("eol"))
        if end is None:
            findings.append(Finding("python", "ok",
                                    f"{label} has no end-of-life date yet"))
        elif end <= today:
            findings.append(Finding(
                "python", "action",
                f"{label} reached end of life on {end.isoformat()}",
                "It no longer receives security fixes. Raise requires-python "
                "in pyproject.toml and the README's Python badge, and move CI "
                "to a supported version."))
        elif end - today <= timedelta(days=EOL_WARNING_DAYS):
            findings.append(Finding(
                "python", "warning",
                f"{label} reaches end of life on {end.isoformat()}, "
                f"in {(end - today).days} days",
                "Plan to raise requires-python in pyproject.toml, and the "
                "README's Python badge, before then."))
        else:
            findings.append(Finding(
                "python", "ok", f"{label} is supported until {end.isoformat()}"))

    released = []
    for entry in entries:
        version = parse_version(str(entry.get("cycle", "")))
        release_date = _iso_date(entry.get("releaseDate"))
        if version and release_date and release_date <= today:
            released.append((_key(version), str(entry["cycle"])))
    tested = [_key(v) for v in map(parse_version, ci_versions) if v]
    if released and tested:
        newest_key, newest = max(released)
        if newest_key > max(tested):
            findings.append(Finding(
                "python", "info",
                f"Python {newest} is the newest release; CI tests "
                f"{', '.join(ci_versions)}",
                "Consider adding it to the matrix in .github/workflows/tests.yml."))
    return findings


# ---------- report ----------
def _clean(text: str) -> str:
    """Make text from a third-party API inert inside the GitHub issue.

    Line breaks are flattened, so a fetched string cannot open a new
    Markdown block (a heading, a list); `<`, `>` and `&` are escaped; and
    `@` is split so it pings nobody. Today every fetched string that
    reaches a title has passed `parse_version` first, but that is an
    invariant of the callers, not something this report should rely on.
    """
    text = re.sub(r"[\r\n]+", " ", text)
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("@", "@​"))


def render_report(findings: list[Finding], today: date) -> str:
    lines = [
        "# Dependency and runtime update report",
        "",
        f"Checked on {today.isoformat()} by `tools/check_updates.py`, which "
        "runs weekly from `.github/workflows/update-check.yml`. Python "
        "packages and GitHub Actions are bumped separately, by Dependabot "
        "pull requests.",
        "",
    ]
    for level in LEVELS:
        group = [f for f in findings if f.level == level]
        if not group:
            continue
        lines += [f"## {_HEADINGS[level]}", ""]
        for finding in group:
            lines.append(f"- **{_clean(finding.title)}**")
            if finding.detail:
                lines.append(f"  {_clean(finding.detail)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def needs_attention(findings: Iterable[Finding]) -> bool:
    return any(f.level in ("action", "warning") for f in findings)


# ---------- entry point ----------
def run_checks(repo: Path, today: date) -> list[Finding]:
    vendor = read_vendor_pins(
        (repo / "web" / "vendor_pyodide.py").read_text(encoding="utf-8"))
    assets = json.loads(
        (repo / "web" / "pyodide-assets.json").read_text(encoding="utf-8"))
    desktop = desktop_requirements(
        (repo / "requirements.txt").read_text(encoding="utf-8"))
    floor = python_floor((repo / "pyproject.toml").read_text(encoding="utf-8"))
    ci = ci_python_versions([(repo / TEST_WORKFLOW).read_text(encoding="utf-8")])

    findings: list[Finding] = []
    try:
        releases = fetch_json(PYODIDE_RELEASES_URL)
    except Exception as exc:  # noqa: BLE001 -- report it, never crash the run
        findings.append(Finding("pyodide", "warning",
                                "Pyodide's releases could not be listed",
                                _describe(exc)))
    else:
        findings += check_pyodide(
            vendor.pyodide, vendor.packages, releases,
            fetch_lock=lambda tag: fetch_json(PYODIDE_LOCK_URL.format(version=tag)),
            native_wheels=vendor.pypi_wheel_files,
            fetch_json=lambda url: fetch_json(url))
    findings += check_browser_parity(browser_versions(assets), desktop)
    findings += check_pypi_wheels(vendor.pypi_wheels,
                                  fetch_json=lambda url: fetch_json(url),
                                  files=vendor.pypi_wheel_files)
    if floor is None:
        findings.append(Finding(
            "python", "warning",
            "requires-python was not found in pyproject.toml",
            "The Python floor is not being checked against end of life."))
    try:
        eol = fetch_json(PYTHON_EOL_URL)
    except Exception as exc:  # noqa: BLE001 -- report it, never crash the run
        findings.append(Finding("python", "warning",
                                "Python's end-of-life dates could not be fetched",
                                _describe(exc)))
    else:
        findings += check_python(floor, ci, eol, today)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check MERIDIAN's pinned runtimes and dependencies.")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT,
                        help="repository root (default: this checkout)")
    parser.add_argument("--report", type=Path,
                        help="also write the Markdown report to this file")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        findings = run_checks(args.repo, args.today)
    except Exception as exc:  # noqa: BLE001 -- a broken check must still report
        # A missing or reshaped local file. Reported as an action so the
        # issue opens and says so, instead of the workflow failing and the
        # issue going quietly stale.
        findings = [Finding(
            "self", "action", "The weekly update check could not run",
            f"{_describe(exc)}. Fix tools/check_updates.py, or the file it "
            "reads, so the report can be produced again.")]
    report = render_report(findings, args.today)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print(report)

    # The workflow opens or updates its issue when this is true, and closes
    # it only when this is explicitly false.
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"attention={'true' if needs_attention(findings) else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
