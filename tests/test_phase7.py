"""Phase 7 helpers: dead-link check of the report documents and log-span runtimes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dead_links_found_and_externals_ignored(tmp_path: Path) -> None:
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "a.json").write_text("{}")
    doc = tmp_path / "doc.md"
    doc.write_text("[ok](results/a.json) [gone](results/b.json) ![fig](missing.png) "
                   "[web](https://example.org/x) [anchor](#sec) [ok2](results/a.json#k)")
    assert _load("21_check_links").dead_links(doc) == ["results/b.json", "missing.png"]


def test_log_span_uses_first_and_last_timestamp(tmp_path: Path) -> None:
    f = tmp_path / "x.log"
    f.write_text("Running as unit\n2026-01-01 00:00:00,1 INFO a\nno stamp\n"
                 "2026-01-01 01:30:00,2 INFO b\n")
    assert _load("20_runtimes").log_span(f) == 5400.0
    f.write_text("2026-01-01 00:00:00 only one\n")
    assert _load("20_runtimes").log_span(f) is None
