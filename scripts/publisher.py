"""Commit and push per-issue assets so GitHub raw URLs become live."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

from scripts.config import PROJECT_ROOT

log = logging.getLogger(__name__)


def _git_timeout() -> int:
    """Editor-tunable timeout (seconds) for any single git call.

    Default 120s -- generous for slow remotes (hotel Wi-Fi, university
    VPN). Set MERIDIAN_GIT_TIMEOUT to override (e.g. "300" for very
    slow CI pushes, "10" for snappy local-only checks).
    """
    raw = os.environ.get("MERIDIAN_GIT_TIMEOUT", "120")
    try:
        return max(5, int(raw))
    except ValueError:
        log.warning("Invalid MERIDIAN_GIT_TIMEOUT=%r -- using 120s.", raw)
        return 120


def _run(cmd: list[str], cwd: Path = PROJECT_ROOT) -> str:
    """Run a git command with a configurable timeout (default 120s)
    so a stale remote cannot hang the editor's pipeline indefinitely."""
    log.debug("Running: %s", shlex.join(cmd))
    result = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True,
        check=False, timeout=_git_timeout(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {shlex.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def is_git_repo(path: Path = PROJECT_ROOT) -> bool:
    try:
        _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
        return True
    except RuntimeError:
        return False


def has_changes_in(rel_path: str, cwd: Path = PROJECT_ROOT) -> bool:
    out = _run(["git", "status", "--porcelain", "--", rel_path], cwd=cwd)
    return bool(out.strip())


def publish_assets(issue: int, *, push: bool = True,
                   cwd: Path = PROJECT_ROOT) -> str | None:
    """Stage, commit, and (optionally) push assets/issue-<N>/.

    Returns the commit SHA if a commit was created; None if there was
    nothing to commit.

    Issue numbers <= 0 are rejected: `issue-0` is the conventional
    sandbox / scratch directory used during development, and pushing
    its contents (test images, manifest.json with PII like dean name +
    subject snippets) to the public repo is almost never intentional.
    Editors number real issues from 1.
    """
    # Round-9 security MEDIUM 5: explicit type check rejects
    # non-int inputs (`0.5`, `"3"`) up front. Without this, e.g.
    # `publish_assets(0.5)` would silently produce path
    # `assets/issue-0.5/` on the filesystem and fail later with a
    # FileNotFoundError further down -- worse error message AND
    # opens a string-coercion attack surface for any future caller
    # that accepts user input. Reject `bool` explicitly: `bool` is
    # a subclass of `int`, but `publish_assets(True)` should never
    # reach the filesystem.
    if isinstance(issue, bool) or not isinstance(issue, int):
        # Cap the repr to 80 chars so a caller passing a large dict /
        # numpy array / arbitrary object can't blow up logs or leak
        # PII via this exception (round-10 security LOW 2).
        bad = repr(issue)
        if len(bad) > 80:
            bad = bad[:77] + "..."
        raise TypeError(
            f"issue must be a positive integer -- got "
            f"{type(issue).__name__} {bad}"
        )
    if issue <= 0:
        raise ValueError(
            f"Refusing to publish issue {issue}: real issues are "
            "numbered from 1. issue-0 is reserved for local "
            "development sandbox; publishing it would push test "
            "artefacts (images + manifest with names) to the "
            "public repository."
        )

    rel = f"assets/issue-{issue}"
    asset_dir = cwd / rel
    if not asset_dir.exists():
        raise FileNotFoundError(f"No such directory: {asset_dir}")

    if not is_git_repo(cwd):
        raise RuntimeError(f"Not a git repository: {cwd}")

    if not has_changes_in(rel, cwd):
        log.info("No changes in %s — nothing to publish.", rel)
        return None

    _run(["git", "add", rel], cwd=cwd)
    _run([
        "git", "commit", "-m", f"chore: publish issue-{issue} assets",
    ], cwd=cwd)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=cwd)
    if push:
        _run(["git", "push"], cwd=cwd)
    return sha


__all__ = ["publish_assets", "is_git_repo", "has_changes_in"]
