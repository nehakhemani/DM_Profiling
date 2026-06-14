from __future__ import annotations

import sys

from .config import Settings
from .discovery import run_discovery
from .executor import execute_plan
from .extractor import extract_entity_config
from .intake_reader import read_intake
from .introspection import get_schema_metadata
from .normalizer import normalize_results
from .reviewer import run_review_loop
from .planner import plan_profiling
from .sql_writer import write_profiling_sql
from .validation import build_identifier_whitelist, validate_config
from .visualizer import render_dashboard


def run(input_path: str, settings: Settings) -> None:
    """
    End-to-end pipeline orchestration. This is the final orchestration code —
    it is entity-agnostic and driven entirely by EntityConfig and stage interfaces.
    Stubs are replaced one phase at a time; this function is not rewritten.
    """
    run_dir = str(settings.run_dir())
    run_id = settings.run_id

    # Stage 1 — Read intake text
    raw_text = read_intake(input_path)

    # Stage 2 — Extract entity config from plain text
    config, clarifications = extract_entity_config(raw_text, settings)
    if clarifications:
        print("Clarification questions (edit intake and rerun):\n")
        for i, q in enumerate(clarifications, 1):
            print(f"  {i}. {q}")
        sys.exit(1)

    # Stage 3a — Introspect schema (used by validation and planner)
    schema_meta = get_schema_metadata(config, settings)
    whitelist = build_identifier_whitelist(schema_meta)

    # Stage 3b — Validate config against live schema; save configs/{entity}.json
    config, questions = validate_config(config, schema_meta, settings)
    if questions:
        print("Validation questions (edit intake and rerun):\n")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")
        sys.exit(1)

    # Stage 4 — Depth-1 discovery of related tables
    discovered_tables = run_discovery(config, settings)

    # Add discovered table FQNs to whitelist so join_analysis targets pass validation
    whitelist |= {dt.fqn for dt in discovered_tables}

    # Stage 5 — LLM Planner: produce a validated ProfilingPlan
    plan = plan_profiling(config, schema_meta, discovered_tables, settings)

    # Stage 6 — Generate SQL file (always written; run in VS Code Snowflake extension)
    sql_path = write_profiling_sql(plan, config, run_id, whitelist, run_dir)
    print(f"  SQL file       -> {sql_path}")

    if settings.generate_sql:
        print("\nSQL file written. Open it in VS Code and run with the Snowflake extension.")
        print("Export each result set as CSV / Excel for further analysis.")
        return

    # Stage 7 — Execute queries (harness: fixture; from_results: read pre-run CSVs; real: future)
    if settings.from_results:
        print(f"  Loading CSVs from {settings.results_dir}/")
    raw_results = execute_plan(plan, config, whitelist, settings, run_id)

    # Stage 8 — Normalize raw rows into MetricResult records
    metrics = normalize_results(raw_results, config.entity, settings)

    # Stage 9 + 10 — Generate insights then iterative review loop
    reviewed_report = run_review_loop(config, plan, metrics, settings, run_id)

    # Stage 11 — Render report.md and dashboard.html
    render_dashboard(reviewed_report, metrics, discovered_tables, config, run_id, run_dir)

    print(f"\nRun complete: {run_dir}/")
    print(f"  report.md      -> {run_dir}/report.md")
    print(f"  dashboard.html -> {run_dir}/dashboard.html")
    print(f"  review status  -> {reviewed_report.review_status} ({reviewed_report.iterations} iteration(s))")
