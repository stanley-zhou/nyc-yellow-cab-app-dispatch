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


def test_compact_into_drops_stale_objects_and_verifies_the_copy(tmp_path: Path) -> None:
    import duckdb

    wh = tmp_path / "warehouse.duckdb"
    con = duckdb.connect(str(wh))   # the catalog is named after the file stem, not "main"
    con.execute("create table fct_a as select range as x from range(1000)")
    con.execute("create view stg_b as select x from fct_a")
    con.execute("create view int_old as select 1 as y")       # not a dbt node any more
    con.execute("insert into fct_a select range from range(10)")
    con.execute("delete from fct_a where x < 500")             # free blocks to reclaim
    stale, _, after, counts, live, ok = _load("22_compact_warehouse").compact_into(
        con, wh.stem, {"fct_a", "stg_b"}, tmp_path / "fresh.duckdb")
    con.close()
    assert ok and stale == {"int_old": "VIEW"} and set(live) == {"fct_a", "stg_b"}
    assert counts == {"fct_a": {"rows": 500, "rows_copy": 500}} and after["used_blocks"] >= 0
    chk = duckdb.connect(str(tmp_path / "fresh.duckdb"), read_only=True)
    assert chk.execute("select count(*) from stg_b").fetchone()[0] == 500
    chk.close()
