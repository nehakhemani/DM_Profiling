from __future__ import annotations

import json

from .config import Settings
from .models import EntityConfig, ProfilingPlan


def execute_plan(
    plan: ProfilingPlan,
    config: EntityConfig,
    validated_identifiers: set[str],
    settings: Settings,
    run_id: str,
) -> list[dict]:
    """
    Generates SQL for each task via sql_generator, executes against Snowflake,
    and returns one result dict per query execution:
        {task, sql, rows, status, error}

    A failed query does NOT abort the run — it is logged and execution continues.

    Harness: loads tests/fixtures/raw_query_results.json.
    Real (Phase 7): single Snowflake connection; sequential execution; per-query
    timeout; persists raw JSONL under runs/{run_id}/.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("raw_query_results.json").read_text(encoding="utf-8"))
        return raw

    raise NotImplementedError("Live executor not yet implemented — use --harness")
