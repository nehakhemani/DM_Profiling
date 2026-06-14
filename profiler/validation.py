from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .models import EntityConfig, TableMeta


def build_identifier_whitelist(schema_meta: list[TableMeta]) -> set[str]:
    """
    Builds the set of allowed identifiers (table FQNs and FQN.column strings)
    from validated schema metadata. Every identifier that reaches a SQL template
    must appear in this set.
    """
    allowed: set[str] = set()
    for tm in schema_meta:
        allowed.add(tm.table)
        for col in tm.columns:
            allowed.add(f"{tm.table}.{col.column}")
    return allowed


def validate_config(
    config: EntityConfig,
    schema_meta: list[TableMeta],
    settings: Settings,
) -> tuple[EntityConfig, list[str]]:
    """
    Validates every table, record key, match column, and rule field in config
    against the introspected schema_meta. Returns (config, questions).

    If questions is non-empty the pipeline must print them and exit.
    On success, saves config to configs/{entity}.json.

    Harness: returns (config, []) — assumes fixture schema is already consistent.
    Real (Phase 4): performs full Definition-of-Ready checks per §2.3.
    """
    if settings.harness:
        _save_config(config, settings)
        return config, []

    raise NotImplementedError("Live validation not yet implemented — use --harness")


def _save_config(config: EntityConfig, settings: Settings) -> None:
    out = Path(settings.configs_dir) / f"{config.entity.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(config.model_dump_json(indent=2), encoding="utf-8")
