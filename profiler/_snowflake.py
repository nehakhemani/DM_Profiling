from __future__ import annotations

import re
import tomllib
from pathlib import Path

import snowflake.connector

# Hard limit: all Snowflake statements must finish within 60 seconds.
_STATEMENT_TIMEOUT_S = 60

# Only these SQL command types are permitted — no DDL or DML.
_ALLOWED_STARTS = re.compile(
    r"^\s*(SELECT|WITH|SHOW|DESCRIBE|DESC)\b",
    re.IGNORECASE,
)


def connect(profile: str = "SPARKNZ-DATA") -> snowflake.connector.SnowflakeConnection:
    """
    Opens a Snowflake connection via externalbrowser SSO and immediately sets
    a 60-second statement timeout for the session.
    """
    cfg = _load_profile(profile)
    conn = snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        authenticator=cfg.get("authenticator", "externalbrowser"),
        role=cfg.get("role") or None,
        warehouse=cfg.get("warehouse") or None,
    )
    conn.cursor().execute(
        f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {_STATEMENT_TIMEOUT_S}"
    )
    return conn


def safe_execute(cur, sql: str):
    """
    Executes sql only if it is a read-only statement (SELECT / WITH / SHOW / DESCRIBE).
    Raises ValueError for any DDL or DML before it reaches Snowflake.
    """
    if not _ALLOWED_STARTS.match(sql):
        first_word = sql.strip().split()[0].upper() if sql.strip() else "(empty)"
        raise ValueError(
            f"Blocked non-SELECT statement reaching Snowflake: {first_word}... "
            "Only SELECT/WITH/SHOW/DESCRIBE are permitted."
        )
    return cur.execute(sql)


def _load_profile(name: str) -> dict:
    path = Path.home() / ".snowflake" / "connections.toml"
    if not path.exists():
        raise FileNotFoundError(f"Snowflake connections config not found: {path}")
    with open(path, "rb") as f:
        connections = tomllib.load(f)
    if name not in connections:
        raise KeyError(f"Connection profile '{name}' not found in {path}")
    return connections[name]
