"""Load `config/project.yaml` and resolve repo-relative paths.

Every date, threshold and path used by the pipeline comes from this file; code never hard-codes
them.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_ENV = "TAXI_SHOCK_CONFIG"


def repo_root() -> Path:
    """Return the repository root (the first parent holding `pyproject.toml`)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "config").is_dir():
            return parent
    raise FileNotFoundError("Could not locate the repository root from " + str(here))


@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict[str, Any]:
    """Read the project config. `TAXI_SHOCK_CONFIG` overrides the default location."""
    cfg_path = Path(path or os.environ.get(CONFIG_ENV, repo_root() / "config" / "project.yaml"))
    with cfg_path.open(encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)
    return cfg


def path(key: str, cfg: dict[str, Any] | None = None) -> Path:
    """Absolute path for a key under `paths:` (or a dotted key such as `smoke.results_dir`)."""
    cfg = cfg or load_config()
    if "." in key:
        section, sub = key.split(".", 1)
        rel = cfg[section][sub]
    else:
        rel = cfg["paths"][key]
    return repo_root() / rel
