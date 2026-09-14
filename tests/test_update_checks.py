"""The weekly check that keeps MERIDIAN's dependencies from going stale.

`tools/check_updates.py` runs every Monday from
`.github/workflows/update-check.yml` and keeps one GitHub issue current.
Dependabot already bumps `requirements*.txt` and the workflow actions;
this covers what Dependabot cannot see:

  * the Pyodide runtime the browser build is pinned to, and whether a
    newer one still ships every package the page loads -- `css-inline`
    above all, which the whole email layout depends on;
  * the browser build's package versions against the desktop's
    requirements, since the two must render the same newsletter;
  * the wheel vendored straight from PyPI (`python-docx`);
  * how close the supported Python versions are to end of life.

Everything here is offline: network access is injected, so these tests
pin the decisions, not the state of the internet.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tools import check_updates as cu

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------- parsing ----------
@pytest.mark.parametrize("text, expected", [
    ("0.29.4", (0, 29, 4)),
    ("314.0.7", (314, 0, 7)),
    ("v1.2.0", (1, 2, 0)),
    ("3.10", (3, 10)),
    ("308", (308,)),
    ("315.0.0a2", None),      # pre-releases are never offered
    ("6.1.0rc1", None),
    ("1.3.0b1", None),
    ("1.0.dev3", None),
    ("", None),
    ("latest", None),
])
def test_parse_version_accepts_final_releases_only(text, expected):
    assert cu.parse_version(text) == expected


VENDOR_SRC = '''
PYODIDE_VERSION = "0.29.4"
PACKAGES = ("css-inline", "jinja2", "beautifulsoup4", "pillow", "lxml")
PYPI_WHEELS = {
    "python_docx-1.2.0-py3-none-any.whl":
        "https://files.pythonhosted.org/packages/py3/p/python-docx/"
        "python_docx-1.2.0-py3-none-any.whl",
}
'''


def test_reads_the_pinned_runtime_from_the_vendor_script():
    pins = cu.read_vendor_pins(VENDOR_SRC)
    assert pins.pyodide == "0.29.4"
    assert pins.packages == ("css-inline", "jinja2", "beautifulsoup4",
                             "pillow", "lxml")
    assert pins.pypi_wheels == {"python-docx": "1.2.0"}


def test_the_real_vendor_script_still_parses():
    """If `web/vendor_pyodide.py` is reshaped, the weekly check must fail
    loudly here rather than silently report nothing."""
    pins = cu.read_vendor_pins(
        (REPO_ROOT / "web" / "vendor_pyodide.py").read_text(encoding="utf-8"))
    assert cu.parse_version(pins.pyodide)
    assert "css-inline" in pins.packages
    assert "python-docx" in pins.pypi_wheels


def test_browser_versions_come_from_the_hash_file_wheel_names():
    assets = {"files": {
        "css_inline-0.16.0-cp39-abi3-pyodide_2025_0_wasm32.whl": "x",
        "lxml-6.0.2-cp313-cp313-pyemscripten_2025_0_wasm32.whl": "x",
        "python_docx-1.2.0-py3-none-any.whl": "x",
        "pyodide.asm.wasm": "x",
        "pyodide-lock.json": "x",
    }}
    assert cu.browser_versions(assets) == {
        "css-inline": "0.16.0", "lxml": "6.0.2", "python-docx": "1.2.0"}


REQS = '''# a comment
python-docx==1.2.0
Jinja2>=3.1.6
css-inline==0.14.1
lxml>=6.1.0   # trailing comment
tomli>=2.0.1; python_version < "3.11"
pywin32==308; platform_system == "Windows"

-r other.txt
'''


def test_desktop_requirements_are_parsed_with_normalised_names():
    assert cu.desktop_requirements(REQS) == {
        "python-docx": ("==", "1.2.0"),
        "jinja2": (">=", "3.1.6"),
        "css-inline": ("==", "0.14.1"),
        "lxml": (">=", "6.1.0"),
        "tomli": (">=", "2.0.1"),
        "pywin32": ("==", "308"),
    }


def test_reads_python_versions_from_pyproject_and_workflows():
    assert cu.python_floor('[project]\nrequires-python = ">=3.10"\n') == "3.10"
    workflows = [
        '        python-version: ["3.12"]\n',
        "          python-version: '3.12'\n",
        "          python-version: ${{ matrix.python-version }}\n",
    ]
    assert cu.ci_python_versions(workflows) == ["3.12"]


# ---------- browser build vs desktop ----------
def _flagged(findings):
    return [f for f in findings if f.level != "ok"]


def test_parity_flags_a_browser_package_below_a_desktop_floor():
    """The desktop floors carry security fixes (lxml's is an XXE CVE); a
    browser build below one is shipping the vulnerable version."""
    (f,) = _flagged(cu.check_browser_parity(
        browser={"lxml": "6.0.2", "jinja2": "3.1.6"},
        desktop={"lxml": (">=", "6.1.0"), "jinja2": (">=", "3.1.6")}))
    assert f.level == "warning"
    assert "lxml" in f.title and "6.0.2" in f.title and "6.1.0" in f.title


def test_parity_flags_exact_pins_that_differ_between_the_builds():
    (f,) = _flagged(cu.check_browser_parity(
        browser={"css-inline": "0.16.0", "python-docx": "1.2.0"},
        desktop={"css-inline": ("==", "0.14.1"),
                 "python-docx": ("==", "1.2.0")}))
    assert f.level == "warning" and "css-inline" in f.title


def test_parity_ignores_packages_only_one_build_has():
    assert not _flagged(cu.check_browser_parity(
        browser={"markupsafe": "3.0.2"},
        desktop={"requests": (">=", "2.33.0")}))


# ---------- Pyodide ----------
NEEDED = ("css-inline", "jinja2", "lxml")


def _releases(*tags, pre=()):
    return [{"tag_name": t, "prerelease": t in pre, "draft": False}
            for t in tags]


def _lock(*names):
    return {"packages": {n: {"name": n, "version": "1.0"} for n in names}}


def test_pyodide_is_current_when_nothing_newer_exists():
    findings = cu.check_pyodide("0.29.4", NEEDED, _releases("0.29.4", "0.29.3"),
                                fetch_lock=pytest.fail)
    assert [f.level for f in findings] == ["ok"]


def test_a_patch_release_on_the_pinned_line_is_actionable():
    (f,) = cu.check_pyodide("0.29.4", NEEDED, _releases("0.29.5", "0.29.4"),
                            fetch_lock=pytest.fail)
    assert f.level == "action" and "0.29.5" in f.title


def test_a_newer_pyodide_without_css_inline_is_reported_as_blocked():
    (f,) = cu.check_pyodide(
        "0.29.4", NEEDED,
        _releases("314.0.7", "315.0.0a2", "0.29.4", pre=("315.0.0a2",)),
        fetch_lock=lambda version: _lock("jinja2", "lxml"))
    assert f.level == "info"
    assert "314.0.7" in f.title and "css-inline" in f.detail


def test_a_newer_pyodide_with_every_package_is_actionable():
    asked = []
    (f,) = cu.check_pyodide(
        "0.29.4", NEEDED, _releases("314.0.7", "0.29.4"),
        fetch_lock=lambda version: asked.append(version) or _lock(*NEEDED))
    assert f.level == "action" and "314.0.7" in f.title
    assert asked == ["314.0.7"]


def test_prereleases_and_drafts_are_never_offered():
    releases = _releases("315.0.0a2", "0.29.4", pre=("315.0.0a2",))
    releases.append({"tag_name": "0.29.9", "prerelease": False, "draft": True})
    findings = cu.check_pyodide("0.29.4", NEEDED, releases,
                                fetch_lock=pytest.fail)
    assert [f.level for f in findings] == ["ok"]


def test_an_unreachable_lockfile_is_a_warning_not_a_crash():
    def unreachable(version):
        raise OSError("CDN down")
    (f,) = cu.check_pyodide("0.29.4", NEEDED, _releases("314.0.7", "0.29.4"),
                            fetch_lock=unreachable)
    assert f.level == "warning" and "314.0.7" in f.title


# ---------- wheels vendored from PyPI ----------
def test_a_vendored_wheel_behind_pypi_is_actionable():
    (f,) = cu.check_pypi_wheels(
        {"python-docx": "1.2.0"},
        fetch_json=lambda url: {"info": {"version": "1.3.0"}})
    assert f.level == "action"
    assert "python-docx" in f.title and "1.3.0" in f.title


@pytest.mark.parametrize("latest", ["1.2.0", "1.3.0b1"])
def test_a_vendored_wheel_that_is_current_is_ok(latest):
    (f,) = cu.check_pypi_wheels(
        {"python-docx": "1.2.0"},
        fetch_json=lambda url: {"info": {"version": latest}})
    assert f.level == "ok"


def test_a_pypi_lookup_failure_is_a_warning():
    def unreachable(url):
        raise OSError("PyPI down")
    (f,) = cu.check_pypi_wheels({"python-docx": "1.2.0"},
                                fetch_json=unreachable)
    assert f.level == "warning"


# ---------- Python ----------
EOL = [
    {"cycle": "3.14", "eol": "2030-10-31", "releaseDate": "2025-10-07"},
    {"cycle": "3.12", "eol": "2028-10-31", "releaseDate": "2023-10-02"},
    {"cycle": "3.10", "eol": "2026-10-31", "releaseDate": "2021-10-04"},
    {"cycle": "3.9", "eol": "2025-10-31", "releaseDate": "2020-10-05"},
    {"cycle": "3.15", "eol": False, "releaseDate": "2026-10-01"},  # not out yet
]
TODAY = date(2026, 9, 14)


def test_a_python_floor_close_to_end_of_life_is_a_warning():
    findings = cu.check_python("3.10", ["3.12"], EOL, today=TODAY)
    (floor,) = [f for f in findings if "3.10" in f.title]
    assert floor.level == "warning" and "2026-10-31" in floor.title


def test_a_python_version_past_end_of_life_is_actionable():
    findings = cu.check_python("3.9", ["3.12"], EOL, today=TODAY)
    (floor,) = [f for f in findings if "3.9" in f.title]
    assert floor.level == "action"


def test_supported_pythons_are_ok_and_a_newer_release_is_informational():
    findings = cu.check_python("3.12", ["3.12"], EOL, today=TODAY)
    assert {f.level for f in findings} <= {"ok", "info"}
    newer = [f for f in findings if f.level == "info"]
    assert newer and "3.14" in newer[0].title   # 3.15 is not released yet


def test_a_python_version_without_eol_data_is_a_warning():
    findings = cu.check_python("3.99", ["3.12"], EOL, today=TODAY)
    assert any(f.level == "warning" and "3.99" in f.title for f in findings)


# ---------- report ----------
def test_report_puts_the_most_urgent_first_and_signals_attention():
    findings = [
        cu.Finding("python", "ok", "Python 3.12 is supported until 2028-10-31"),
        cu.Finding("parity", "warning", "lxml: browser 6.0.2 is below desktop >=6.1.0"),
        cu.Finding("pyodide", "action", "Pyodide 0.29.5 is available", "Bump it."),
    ]
    report = cu.render_report(findings, today=TODAY)
    assert report.index("Pyodide 0.29.5") < report.index("lxml:") \
        < report.index("Python 3.12")
    assert cu.needs_attention(findings)
    assert not cu.needs_attention([findings[0]])
    assert not cu.needs_attention([cu.Finding("pyodide", "info", "blocked")])


def test_report_never_renders_markup_or_mentions_from_fetched_text():
    """Titles carry version strings from third-party APIs into a GitHub
    issue; they must not become HTML or ping anyone."""
    f = cu.Finding("pypi", "action",
                   "python-docx <img src=x onerror=alert(1)> by @someone")
    report = cu.render_report([f], today=TODAY)
    assert "<img" not in report
    assert "@someone" not in report


# ---------- end to end ----------
def test_main_checks_the_real_repository_with_a_fake_network(tmp_path, monkeypatch):
    def fake_fetch_json(url: str):
        if "api.github.com/repos/pyodide/pyodide/releases" in url:
            return _releases("314.0.7", "0.29.4")
        if "pyodide-lock.json" in url:
            return _lock("jinja2", "lxml", "pillow", "beautifulsoup4")
        if "pypi.org/pypi/" in url:
            return {"info": {"version": "1.2.0"}}
        if "endoflife.date" in url:
            return EOL
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(cu, "fetch_json", fake_fetch_json)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    report = tmp_path / "report.md"

    assert cu.main(["--repo", str(REPO_ROOT), "--report", str(report),
                    "--today", "2026-09-14"]) == 0

    text = report.read_text(encoding="utf-8")
    assert text.startswith("# Dependency and runtime update report")
    assert "314.0.7" in text and "css-inline" in text     # blocked upgrade
    assert "Python 3.10" in text                          # floor near EOL
    assert "attention=true" in output.read_text(encoding="utf-8")
