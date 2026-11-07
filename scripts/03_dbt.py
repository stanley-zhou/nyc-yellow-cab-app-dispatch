"""Run dbt (deps/run/test/build) with vars from config/project.yaml.

Usage:
    python scripts/03_dbt.py build            # full warehouse  (data/warehouse.duckdb)
    python scripts/03_dbt.py build --smoke    # sample month    (data/smoke.duckdb)
    python scripts/03_dbt.py test
"""

from __future__ import annotations

import argparse
import sys

from taxi_shock.dbt_runner import run_dbt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", nargs="+", help="dbt command and extra arguments")
    ap.add_argument("--smoke", action="store_true", help="use the smoke month and warehouse")
    args, extra = ap.parse_known_args()
    try:
        run_dbt([*args.command, *extra], smoke=args.smoke)
    except Exception as err:  # surface dbt's non-zero exit as our own
        print(f"dbt failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
