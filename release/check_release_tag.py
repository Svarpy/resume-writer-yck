"""Resolve whether HEAD should publish a GitHub Release.

Prints ``should_release=true|false`` and ``version=vX.Y.Z`` for Actions.

A release is published only when a git tag equal to ``APP_VERSION`` points at
the current HEAD commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from resume_writer.constants import APP_VERSION  # noqa: E402
from resume_writer.version import normalize_version  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def tag_points_at_head(tag: str) -> bool:
    try:
        # Quiet existence check avoids noisy "ambiguous argument" fatals.
        _git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
        tag_sha = _git("rev-list", "-n", "1", tag)
        head_sha = _git("rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        return False
    return bool(tag_sha) and tag_sha == head_sha


def main() -> int:
    version = normalize_version(APP_VERSION)
    should = tag_points_at_head(version)
    print(f"version={version}")
    print(f"should_release={'true' if should else 'false'}")
    if should:
        print(f"Tag {version} matches HEAD; release builds will run.")
    else:
        print(
            f"No tag {version} on HEAD; tests-only (no Release publish).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
