"""dbt_project.yml var defaults must equal the values the pipeline derives from project.yaml."""

from pathlib import Path

import yaml

from taxi_shock.config import load_config, repo_root
from taxi_shock.dbt_runner import dbt_vars

PATH_VARS = {"yellow_glob", "weather_glob", "zone_lookup_csv", "zones_cbd_csv"}


def test_dbt_defaults_match_config():
    project = yaml.safe_load((repo_root() / "dbt" / "dbt_project.yml").read_text())["vars"]
    derived = dbt_vars(load_config())
    assert set(project) == set(derived)
    for key, val in derived.items():
        if key in PATH_VARS:
            assert (repo_root() / "dbt" / project[key]).resolve() == Path(val).resolve(), key
        else:
            assert project[key] == val, key
