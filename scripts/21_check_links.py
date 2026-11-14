"""Phase 7: every relative link and image in the report documents must point to an existing file.

CLAUDE.md rule 1 asks that every number names its results/ file; this check makes sure the named
files exist (a renamed or deleted result would otherwise leave a dead link in the report).
Checked: README.md, reports/analysis.md, reports/dashboard_spec.md, reports/deferred_items.md.
Exit 1 on any dead link.
"""

from __future__ import annotations

import logging
import re
import sys

from taxi_shock.config import repo_root

LOG = logging.getLogger("links")
DOCS = ("README.md", "reports/analysis.md", "reports/appendix.md", "reports/dashboard_spec.md",
        "reports/deferred_items.md")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def dead_links(doc) -> list[str]:
    out = []
    for target in LINK.findall(doc.read_text()):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue  # external URL or in-page anchor
        f = (doc.parent / target.split("#")[0]).resolve()
        if not f.exists():
            out.append(target)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root, bad = repo_root(), 0
    for d in DOCS:
        doc = root / d
        if not doc.exists():
            continue
        for t in dead_links(doc):
            LOG.error("%s: dead link %s", d, t)
            bad += 1
    LOG.info("%d dead link(s)", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
