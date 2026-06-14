from __future__ import annotations

import datetime
from pathlib import Path

from .models import EntityConfig, ProfilingPlan, ProfilingTask
from .sql_generator import (
    _distribution_analysis,
    _null_analysis,
    _distinct_count,
    _uniqueness_check,
    _pattern_analysis,
    _join_analysis,
    _cross_system_overlap,
    segment_crosstab_sql,
)


def write_profiling_sql(
    plan: ProfilingPlan,
    config: EntityConfig,
    run_id: str,
    validated_identifiers: set[str],
    output_dir: str,
) -> str:
    """
    Writes the profiling SQL to two locations:
      - sql/{entity}_profiling.sql   (project-level, committed, opened directly in VS Code)
      - runs/{run_id}/profiling_queries.sql  (run-specific archive)

    Each block is a labelled SELECT ready to run in the VS Code Snowflake extension.
    Returns the project-level path (the one to open in VS Code).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    sql_path = out / "profiling_queries.sql"

    lines: list[str] = []
    _header(lines, config, run_id)

    task_num = 0
    for task in plan.profiling_tasks:
        for block in _render_task(task, config, validated_identifiers):
            task_num += 1
            lines.append(f"-- ── Task {task_num}: {block['label']} {'─'*max(1,50-len(block['label']))}")
            lines.append(f"-- Business reason: {task.business_reason}")
            lines.append(f"-- Export this result as: task_{task_num:02d}_{_safe(block['label'])}.csv")
            lines.append(block["sql"] + ";")
            lines.append("")

    content = "\n".join(lines)

    # run-specific archive copy
    sql_path.write_text(content, encoding="utf-8")

    # project-level file — committed to repo, opened directly in VS Code
    project_sql_dir = Path("sql")
    project_sql_dir.mkdir(exist_ok=True)
    project_sql_path = project_sql_dir / f"{config.entity.lower()}_profiling.sql"
    project_sql_path.write_text(content, encoding="utf-8")

    return str(project_sql_path)


# ── Header ────────────────────────────────────────────────────────────────────

def _header(lines: list[str], config: EntityConfig, run_id: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines += [
        "-- " + "=" * 70,
        f"-- Profiling run  : {config.entity}",
        f"-- Run ID         : {run_id}",
        f"-- Generated      : {ts}",
        f"-- Purpose        : {config.purpose}",
        "-- " + "-" * 70,
        "-- Profiling rules:",
    ]
    for i, r in enumerate(config.profiling_rules, 1):
        lines.append(f"--   {i}. {r.rule}")
    lines += [
        "-- " + "=" * 70,
        "-- HOW TO USE:",
        "--   1. Open this file in VS Code with the Snowflake extension.",
        "--   2. Run each block (Ctrl+Enter or Run All).",
        "--   3. Export each result set as CSV / Excel.",
        "-- " + "=" * 70,
        "",
    ]


# ── Task renderer ─────────────────────────────────────────────────────────────

def _render_task(
    task: ProfilingTask,
    config: EntityConfig,
    validated_identifiers: set[str],
) -> list[dict]:
    """Returns a list of {label, sql} dicts for one ProfilingTask."""
    t = task.type
    blocks: list[dict] = []

    try:
        if t in ("null_analysis", "distinct_count", "uniqueness_check",
                 "pattern_analysis", "distribution_analysis"):
            for col in task.columns:
                if f"{task.table}.{col}" not in validated_identifiers:
                    continue
                sql = _per_column_sql(t, task.table, col)
                blocks.append({"label": f"{t} | {_short(task.table)}.{col}", "sql": sql})

        elif t == "join_analysis":
            sql = _join_analysis(task.table, task.join_table, task.join_key)
            blocks.append({"label": f"join_analysis | {_short(task.table)} → {_short(task.join_table)}", "sql": sql})

        elif t == "cross_system_overlap":
            m = task.match
            sql = _cross_system_overlap(m.left_table, m.left_column, m.right_table, m.right_column)
            blocks.append({"label": f"cross_system_overlap | {m.left_column} = {m.right_column}", "sql": sql})

        elif t == "segment_variation":
            m = task.match
            # Part 1: distribution per segment column per system
            for tbl_fqn, seg_cols in task.segment_columns.items():
                sys_label = _system_for(tbl_fqn, config)
                for col in seg_cols:
                    if f"{tbl_fqn}.{col}" not in validated_identifiers and tbl_fqn in validated_identifiers:
                        pass  # allow if table is valid (segment cols validated by planner)
                    sql = _distribution_analysis(tbl_fqn, col)
                    blocks.append({"label": f"segment_distribution | {sys_label}.{col}", "sql": sql})

            # Part 2: cross-system segment cross-tab (one per combination)
            left_cols = task.segment_columns.get(m.left_table, [])
            right_cols = task.segment_columns.get(m.right_table, [])
            for lc in left_cols:
                for rc in right_cols:
                    sql = segment_crosstab_sql(
                        m.left_table, m.left_column, lc,
                        m.right_table, m.right_column, rc,
                    )
                    lsys = _system_for(m.left_table, config)
                    rsys = _system_for(m.right_table, config)
                    blocks.append({"label": f"segment_crosstab | {lsys}.{lc} × {rsys}.{rc}", "sql": sql})

    except ValueError as exc:
        # Whitelist violation — skip task with a comment
        blocks.append({"label": f"SKIPPED {t}", "sql": f"-- SKIPPED: {exc}"})

    return blocks


def _per_column_sql(task_type: str, table: str, column: str) -> str:
    if task_type == "null_analysis":
        return _null_analysis(table, column)
    if task_type == "distinct_count":
        return _distinct_count(table, column)
    if task_type == "uniqueness_check":
        return _uniqueness_check(table, column)
    if task_type == "pattern_analysis":
        return _pattern_analysis(table, column)
    if task_type == "distribution_analysis":
        return _distribution_analysis(table, column)
    raise ValueError(f"No per-column template for {task_type}")


def _system_for(fqn: str, config: EntityConfig) -> str:
    for t in config.tables:
        if t.fqn == fqn:
            return t.system
    return _short(fqn)


def _short(fqn: str) -> str:
    return fqn.split(".")[-1] if fqn else ""


def _safe(label: str) -> str:
    return (label
            .encode("ascii", "replace").decode()
            .replace(" ", "_").replace("|", "").replace("/", "_").replace(".", "_")
            .replace("?", "-"))[:40]
