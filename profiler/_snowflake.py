from __future__ import annotations

import tomllib
from pathlib import Path

import snowflake.connector


def connect(profile: str = "SPARKNZ-DATA") -> snowflake.connector.SnowflakeConnection:
    cfg = _load_profile(profile)
    return snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        authenticator=cfg.get("authenticator", "externalbrowser"),
        role=cfg.get("role") or None,
        warehouse=cfg.get("warehouse") or None,
    )


def _load_profile(name: str) -> dict:
    path = Path.home() / ".snowflake" / "connections.toml"
    if not path.exists():
        raise FileNotFoundError(f"Snowflake connections config not found: {path}")
    with open(path, "rb") as f:
        connections = tomllib.load(f)
    if name not in connections:
        raise KeyError(f"Connection profile '{name}' not found in {path}")
    return connections[name]
