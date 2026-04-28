"""Commit and push per-issue assets so GitHub raw URLs become live."""

from __future__ import annotations

import logging
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
    import os
    raw = os.environ.get("MERIDIAN_GIT_TIMEOUT", "120")
    try:
        return max(5, int(raw))
    except ValueError:
        log.warning("Invalid MERIDIAN_GIT_TIMEOUT=%r -- using 120s.", raw)
        return 120


def _run(cmd: list[str], cwd: Path = PROJECT_ROOT) -> str:
    """Run a git command with a configurable timeout (default 120s)
    so a stale remote cannot hang the editor's pipeline indefinitely."""
    import shlex
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
    """
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
