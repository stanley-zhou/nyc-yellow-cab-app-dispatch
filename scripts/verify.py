"""`make verify PHASE=N`: ruff, pytest, dbt test (phase >= 1; smoke warehouse for phase 0), and
presence of every result file listed for phase N in config/phase_outputs.yaml.

Prints one PASS/FAIL line per check and exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from taxi_shock.config import repo_root


def run(name: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd, cwd=cwd, env=env).returncode == 0
    print(f"=== {name}: {'PASS' if ok else 'FAIL'}", flush=True)
    return ok


def pytest_no_skips(junit: Path) -> bool:
    """From phase 1 a skipped test counts as a failure (PLAN amendment, Phase 1 item 3)."""
    suites = ET.parse(junit).getroot()
    skipped = sum(int(s.get("skipped", 0)) for s in suites.iter("testsuite"))
    print(f"=== pytest skipped tests: {skipped} ({'PASS' if skipped == 0 else 'FAIL'})")
    return skipped == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, required=True)
    phase = ap.parse_args().phase
    root = repo_root()
    bindir = Path(sys.executable).parent
    results: dict[str, bool] = {}
    results["ruff"] = run("ruff", [str(bindir / "ruff"), "check", "."], root)
    if phase >= 1:
        junit = root / ".pytest_cache" / "verify_junit.xml"
        env = {**os.environ, "TAXI_SHOCK_REQUIRE_WAREHOUSE": "1"}
        results["pytest"] = run("pytest", [str(bindir / "pytest"), "-q", "-rs",
                                           f"--junitxml={junit}"], root, env)
        results["no_skips"] = pytest_no_skips(junit)
    else:
        results["pytest"] = run("pytest", [str(bindir / "pytest"), "-q"], root)
    dbt_cmd = [sys.executable, "scripts/03_dbt.py", "test"] + (["--smoke"] if phase == 0 else [])
    results["dbt_test"] = run("dbt test", dbt_cmd, root)

    spec = yaml.safe_load((root / "config" / "phase_outputs.yaml").read_text(encoding="utf-8"))
    missing = []
    for rel in spec.get(phase, []):
        p = root / rel
        ok = p.exists() and p.stat().st_size > 0
        print(f"output {'OK     ' if ok else 'MISSING'} {rel}")
        if not ok:
            missing.append(rel)
    results["outputs"] = not missing

    print(f"\n=== verify summary (phase {phase})")
    for k, v in results.items():
        print(f"{k:10s} {'PASS' if v else 'FAIL'}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
