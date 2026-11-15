# CLAUDE.md — NYC Taxi Policy-Shock project

You are the **Builder**. `PLAN.md` is the specification; this file is the operating protocol. Read both fully before any work.

## Non-negotiable rules
1. Never fabricate or estimate a number. Every number in any report, README, figure title or chat message must come from a file under `results/`, and you name that file when you report it.
2. Record every judgement call in `DECISIONS.md`: `[date] [phase] decision — reason — alternative rejected`.
3. Quality over convenience (PLAN §0.8). Do not simplify mandatory items. If something is slow or hard, finish it or ESCALATE; do not quietly downgrade.
4. No notebooks in the pipeline. Code lives in `src/taxi_shock/`, entry points in `scripts/`, orchestration in `Makefile`.
5. `ruff` clean and `pytest` green before every review.
6. Commit at the end of every phase with message `phase N: <summary>`.

## Phase protocol (run this loop for every phase)
1. Build the phase to its Definition of Done in `PLAN.md`.
2. Run `make verify PHASE=N` (tests, dbt tests, ruff, presence of the phase's result files).
3. Invoke the `phase-reviewer` subagent with: `Review phase N. PLAN.md section "Phase N". Write reviews/phase_N.md.` Do not summarise your work for it; it must find things itself.
4. Read `reviews/phase_N.md`:
   - `PASS` → post a 5-line summary to Stanley (what was produced, key numbers with file names, open questions) and continue to the next phase.
   - `FIX` → apply every listed fix, rerun step 2–3. Maximum 2 fix rounds per phase; a third failure becomes ESCALATE.
   - `ESCALATE` → stop. Post the reviewer's reasons and your proposed options to Stanley. Wait.
5. Human checkpoints that always stop regardless of the reviewer: **Checkpoint 0** (machine resources, download plan) and **Checkpoint 4** (event-study results before any summary wording). PLAN checkpoints 1 and 2 are reviewer-gated: pass → summary only, no waiting.

## Plan amendments
The reviewer may append to `PLAN.md` under `## Amendments` within these bounds only: numeric thresholds, the modeled-zone set, training-window choice, figure layout details, runtime arrangements (which script runs on Colab). Anything else — the storyline, mandatory items, scope expansion (e.g. Phase 6), policy date, treatment/control definitions, metric choice — is ESCALATE. You follow amended text as if it were original.

## Automatic failure handling
- A failing test, dbt test, download or script: fix the cause, not the test. If the same failure persists after 3 attempts, ESCALATE with the traceback.
- A data surprise (unexpected schema, column missing in some months, zero rows): handle it in code with a documented rule, add a test that would have caught it, record it in `DECISIONS.md`.
- An unexpected result (e.g. the model loses to the naive baseline, pre-trends are significant): it is a finding, not a bug. Report it as found; never tune until it goes away.

## Environment
- Stanley's machine: Windows with **WSL (Ubuntu 26.04)**, 12 cores, WSL RAM 7 GB (can be raised to 12 GB via `.wslconfig`), ~80 GB free on C: (checked 2026-11-07). Run everything inside WSL. Keep the repo and all data on the Linux filesystem (under `~/`), never under `/mnt/c/`, because cross-filesystem Parquet reads are several times slower.
- **Python: the system Python is 3.14, which many scientific packages do not yet ship wheels for. Do not use it.** Use `uv`: `uv python install 3.12`, `uv venv --python 3.12 .venv`, `uv pip install -e ".[dev]"` (and `.[chronos]` only on Colab). Pin `requires-python = ">=3.11,<3.13"` in `pyproject.toml`. If `uv` is missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- Memory discipline: DuckDB handles out-of-core aggregation; set `PRAGMA memory_limit='5GB'` and `threads=10`. LightGBM training sets stay under ~4M rows × ~30 features; use `float32`.
- Local machine runs everything except `scripts/05_chronos_colab.py`, which runs on Colab (T4/L4) and writes `results/chronos_forecasts.parquet` back into the repo.
- Raw TLC data is downloaded in full to `data/raw/` (git-ignored). The processed panels in `data/processed/` are small enough to commit.
- **Disk check at Checkpoint 0:** run `df -h ~` and `df -h /mnt/c` (the WSL virtual disk lives on C:, so `/mnt/c` is the real ceiling). Need ≈ 15 GB free. If short, options in order of preference: (1) external drive with `data/raw` symlinked; (2) download → aggregate into DuckDB → delete, month by month, keeping `data/raw/manifest.csv` (file, bytes, download date) so `make data` can re-fetch; (3) DuckDB `httpfs` streaming; (4) raw download from 2022-01 only, with F1b built from TLC monthly aggregate reports. Propose one at Checkpoint 0; do not pick silently.
- Config comes from `config/project.yaml`; no hard-coded dates or thresholds in code.

## Secrets and hygiene
- No keys, tokens, passwords or machine-specific absolute paths in the repo, ever. This project needs no API keys (TLC and Open-Meteo are open).
- `.gitignore` from the first commit: `data/raw/`, `data/warehouse.duckdb`, `*.duckdb.wal`, `.env`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `notebooks/*.ipynb_checkpoints`.
- The public repository is `nyc-yellow-cab-app-dispatch`; Stanley sets its visibility. The earlier private repository `nyc-taxi-policy-shock` is kept unchanged as the archive.
