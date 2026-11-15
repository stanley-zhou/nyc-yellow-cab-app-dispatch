"""results/INDEX.md lists every tracked results file exactly once, and nothing else.

Reads the file list from `git ls-files results` and the links in results/INDEX.md.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from taxi_shock.config import repo_root


def tracked_results() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "results"], cwd=repo_root(), check=True,
                             capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    files = [f.removeprefix("results/") for f in out.split()]
    return sorted(f for f in files if f != "INDEX.md")


def test_index_lists_every_results_file_once():
    text = (repo_root() / "results" / "INDEX.md").read_text()
    listed = re.findall(r"^\| \[`[^`]+`\]\(([^)]+)\) \|", text, re.M)
    assert sorted(listed) == tracked_results()
