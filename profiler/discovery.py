from __future__ import annotations

import json

from .config import Settings
from .models import DiscoveredTable, EntityConfig


def run_discovery(config: EntityConfig, settings: Settings) -> list[DiscoveredTable]:
    """
    Depth-1 discovery: finds tables in the same schema that reference any base
    table's record_key column by name.

    Harness: loads tests/fixtures/discovered_tables.json.
    Real (Phase 5): queries INFORMATION_SCHEMA.COLUMNS — metadata only, no data SELECTs.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("discovered_tables.json").read_text(encoding="utf-8"))
        return [DiscoveredTable.model_validate(t) for t in raw]

    raise NotImplementedError("Live discovery not yet implemented — use --harness")
