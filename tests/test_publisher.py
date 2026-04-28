"""Tests for the publisher's safety guards.

The publisher pushes per-issue assets to a public GitHub repo. The
issue-0 sandbox MUST be rejected to prevent accidental leakage of
test artefacts (images + manifest with PII like dean name).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import publisher


@pytest.mark.parametrize("issue", [0, -1, -100])
def test_publisher_rejects_non_positive_issue_numbers(
    issue: int, tmp_path: Path
) -> None:
    """`publish_assets(issue=0)` must raise -- issue-0 is the local
    sandbox/scratch directory; pushing it to the public repo is almost
    never intentional.

    Regression guard for round-8 security MEDIUM."""
    with pytest.raises(ValueError) as exc_info:
        publisher.publish_assets(issue, push=False, cwd=tmp_path)
    msg = str(exc_info.value).lower()
    assert "issue" in msg
    assert ("0" in msg or "1" in msg or "real" in msg)


def test_publisher_accepts_positive_issue_with_missing_dir(
    tmp_path: Path
) -> None:
    """For `issue >= 1` the publisher should run its normal checks
    (here: missing directory) -- verifies the new guard doesn't
    over-block."""
    # The directory doesn't exist, so we expect FileNotFoundError --
    # NOT the new ValueError from the issue guard.
    with pytest.raises(FileNotFoundError):
        publisher.publish_assets(1, push=False, cwd=tmp_path)


# ---------- Bundle 28: type guard ---------------------------------------

def test_publisher_rejects_float_issue(tmp_path: Path) -> None:
    """Round-9 security MEDIUM 5: `publish_assets(0.5)` used to pass
    the `<= 0` numeric guard (0.5 > 0) and produce a path
    `assets/issue-0.5/` on the filesystem before failing later with
    `FileNotFoundError`. Bundle 28 rejects non-int issue numbers up
    front with a clear `TypeError`."""
    with pytest.raises(TypeError, match="issue must be a positive integer"):
        publisher.publish_assets(0.5, push=False, cwd=tmp_path)
    with pytest.raises(TypeError):
        publisher.publish_assets(3.0, push=False, cwd=tmp_path)


def test_publisher_rejects_string_issue(tmp_path: Path) -> None:
    """`publish_assets("3")` would have built an `assets/issue-3/`
    path that LOOKS valid -- a near-miss for the type guard. Reject."""
    with pytest.raises(TypeError):
        publisher.publish_assets("3", push=False, cwd=tmp_path)  # type: ignore[arg-type]


def test_publisher_rejects_bool_issue(tmp_path: Path) -> None:
    """Python booleans are a subclass of int, so the naive
    `isinstance(issue, int)` check would accept `True` (=1) and
    `False` (=0). The guard explicitly excludes bool."""
    with pytest.raises(TypeError):
        publisher.publish_assets(True, push=False, cwd=tmp_path)
    with pytest.raises(TypeError):
        publisher.publish_assets(False, push=False, cwd=tmp_path)


def test_publisher_error_message_explains_why(tmp_path: Path) -> None:
    """The error message must tell the editor *why* issue-0 is
    rejected -- not just refuse silently."""
    with pytest.raises(ValueError) as exc_info:
        publisher.publish_assets(0, push=False, cwd=tmp_path)
    msg = str(exc_info.value)
    # Must mention sandbox / development / numbered-from-1, so an
    # editor seeing this in CLI output can act on it.
    assert any(
        word in msg.lower()
        for word in ("sandbox", "development", "1", "test artefact",
                     "test artifacts", "local")
    ), f"Error message lacks guidance: {msg!r}"
