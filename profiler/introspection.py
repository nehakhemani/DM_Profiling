from __future__ import annotations

import json

from .config import Settings
from .models import EntityConfig, TableMeta


def get_schema_metadata(config: EntityConfig, settings: Settings) -> list[TableMeta]:
    """
    Returns TableMeta for every base table in config.

    Harness: loads tests/fixtures/schema_metadata.json.
    Real (Phase 4): queries INFORMATION_SCHEMA with bound parameters.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("schema_metadata.json").read_text(encoding="utf-8"))
        return [TableMeta.model_validate(t) for t in raw]

    raise NotImplementedError("Live introspection not yet implemented — use --harness")
