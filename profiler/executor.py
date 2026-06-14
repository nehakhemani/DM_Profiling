from __future__ import annotations

import csv as csv_mod
import json
from pathlib import Path

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
    Returns one result dict per plan task.  Each dict contains the task metadata
    and a list of 'blocks' — one block per SQL query that task produced — with the
    CSV rows already loaded.

    Harness: loads tests/fixtures/raw_query_results.json.
    Real: reads pre-executed CSVs from results_dir, paired to plan tasks in order.
    """
    if settings.from_results:
        return _load_csv_results(plan, config, settings)

    if settings.harness:
        raw = json.loads(settings.fixture_path("raw_query_results.json").read_text(encoding="utf-8-sig"))
        return raw

    raise NotImplementedError("Live executor not yet implemented — use --harness or --from-results")


# ── Real mode: read pre-executed CSVs ────────────────────────────────────────

def _load_csv_results(plan: ProfilingPlan, config: EntityConfig, settings: Settings) -> list[dict]:
    results_dir = Path(settings.results_dir)
    results: list[dict] = []
    csv_num = 0

    for task in plan.profiling_tasks:
        blocks_meta = _task_block_meta(task)
        blocks_data: list[dict] = []

        for meta in blocks_meta:
            csv_num += 1
            matches = sorted(results_dir.glob(f"task_{csv_num:02d}_*.csv"))
            if matches:
                rows = _read_csv(matches[0])
                blocks_data.append({**meta, "rows": rows, "status": "success", "error": None})
            else:
                blocks_data.append({**meta, "rows": [], "status": "missing",
                                    "error": f"task_{csv_num:02d}_*.csv not found in {results_dir}"})

        all_ok = all(b["status"] == "success" for b in blocks_data)
        results.append({
            "task": task.model_dump(),
            "status": "success" if all_ok else "partial",
            "error": None,
            "blocks": blocks_data,
        })

    return results


def _task_block_meta(task) -> list[dict]:
    """
    Returns one metadata dict per SQL block the task produces, in the same order
    as sql_writer._render_task.  No SQL is generated here — just the structural
    context the normalizer needs.
    """
    t = task.type
    blocks: list[dict] = []

    if t in ("null_analysis", "distinct_count", "uniqueness_check",
             "pattern_analysis", "distribution_analysis"):
        for col in task.columns:
            blocks.append({"block_kind": t, "table": task.table, "column": col})

    elif t == "join_analysis":
        blocks.append({
            "block_kind": "join_analysis",
            "table": task.table,
            "column": None,
            "join_table": task.join_table,
            "join_key": task.join_key,
        })

    elif t == "cross_system_overlap":
        m = task.match
        blocks.append({
            "block_kind": "cross_system_overlap",
            "table": m.left_table,
            "column": None,
            "match": m.model_dump(),
        })

    elif t == "segment_variation":
        m = task.match
        # Part 1: per-system distributions (same iteration order as sql_writer)
        for tbl, cols in task.segment_columns.items():
            for col in cols:
                blocks.append({"block_kind": "segment_distribution", "table": tbl, "column": col})
        # Part 2: cross-tabs
        left_cols = task.segment_columns.get(m.left_table, [])
        right_cols = task.segment_columns.get(m.right_table, [])
        for lc in left_cols:
            for rc in right_cols:
                blocks.append({
                    "block_kind": "segment_crosstab",
                    "table": m.left_table,
                    "column": None,
                    "left_col": lc,
                    "right_col": rc,
                    "match": m.model_dump(),
                })

    return blocks


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv_mod.DictReader(f)
        return [{k.lower(): _coerce(v) for k, v in row.items()} for row in reader]


def _coerce(v: str):
    if v == "" or v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        pass
    try:
        return float(v)
    except (ValueError, TypeError):
        return v
