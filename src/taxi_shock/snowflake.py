"""Snowflake connection for running the dbt models on Snowflake (PLAN Amendment 4, E3), from
environment variables only. The connector reads the private-key file the environment names; this
module writes nothing.

The variables are set outside the repository (`source ~/.snowflake/taxi.env`): SNOWFLAKE_ACCOUNT,
SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY_PATH (key-pair authentication, unencrypted PKCS#8),
SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA. No value is logged.
"""

from __future__ import annotations

import os

ENV = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH", "SNOWFLAKE_ROLE",
       "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA")


def missing_env() -> list[str]:
    return [k for k in ENV if not os.environ.get(k)]


def connect(schema: str | None = None):
    """Open a Snowflake connection with the role, warehouse and database from the environment."""
    import snowflake.connector

    miss = missing_env()
    if miss:
        raise SystemExit(f"missing environment variables: {', '.join(miss)} "
                         "(source ~/.snowflake/taxi.env)")
    e = os.environ
    return snowflake.connector.connect(
        account=e["SNOWFLAKE_ACCOUNT"], user=e["SNOWFLAKE_USER"],
        private_key_file=e["SNOWFLAKE_PRIVATE_KEY_PATH"], role=e["SNOWFLAKE_ROLE"],
        warehouse=e["SNOWFLAKE_WAREHOUSE"], database=e["SNOWFLAKE_DATABASE"],
        schema=schema or e["SNOWFLAKE_SCHEMA"], session_parameters={"QUERY_TAG": "taxi_shock_e3"},
        client_session_keep_alive=False)
