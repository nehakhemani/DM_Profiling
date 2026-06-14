from __future__ import annotations

import json

from .config import Settings
from .models import DiscoveredTable, EntityConfig, ProfilingPlan, TableMeta


def plan_profiling(
    config: EntityConfig,
    schema_meta: list[TableMeta],
    discovered_tables: list[DiscoveredTable],
    settings: Settings,
) -> ProfilingPlan:
    """
    Generates a ProfilingPlan covering every profiling rule.

    Harness: loads tests/fixtures/profiling_plan.json.
    Real (Phase 6): calls LLM with §5.4 prompts; validates every task against
    schema_meta whitelist; drops invalid tasks with a warning; retries once on
    JSON parse failure.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("profiling_plan.json").read_text(encoding="utf-8"))
        return ProfilingPlan.model_validate(raw)

    raise NotImplementedError("Live planner not yet implemented — use --harness")
