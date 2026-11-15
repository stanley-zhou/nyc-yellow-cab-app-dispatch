"""The README make-target table lists exactly the targets and descriptions of `make help`.

Reads Makefile (each target's `## description`) and the table under "### Make targets" in README.md.
"""

from __future__ import annotations

import re

from taxi_shock.config import repo_root


def makefile_targets() -> list[tuple[str, str]]:
    text = (repo_root() / "Makefile").read_text()
    return re.findall(r"^([a-z][a-z0-9-]*):[^#\n]*## (.*)$", text, re.M)


def readme_targets() -> list[tuple[str, str]]:
    text = (repo_root() / "README.md").read_text()
    section = text.split("### Make targets", 1)[1].split("\n#", 1)[0]
    return re.findall(r"^\| `([a-z][a-z0-9-]*)` \| (.*) \|$", section, re.M)


def test_every_phony_target_has_a_description():
    text = (repo_root() / "Makefile").read_text()
    phony = re.search(r"^\.PHONY:(.*)$", text, re.M).group(1).split()
    assert sorted(phony) == sorted(t for t, _ in makefile_targets())


def test_readme_table_matches_make_help():
    assert readme_targets() == makefile_targets()
