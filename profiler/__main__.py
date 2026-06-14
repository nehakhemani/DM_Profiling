from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import Settings
from .pipeline import run


def _load_dotenv() -> None:
    """Load key=value pairs from .env if it exists (no external dependency)."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(
        prog="python -m profiler",
        description="AI Data Profiling Agent for Snowflake",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # profiler run
    run_p = sub.add_parser("run", help="Full pipeline end-to-end")
    run_p.add_argument("--input", required=True, help="Path to intake text file")
    run_p.add_argument("--harness", action="store_true", help="Use fixture stubs (no Snowflake, no LLM)")
    run_p.add_argument("--generate-sql", action="store_true", help="Write profiling_queries.sql and exit")
    run_p.add_argument("--plan-only", action="store_true", help="Stop after plan + SQL generation")
    run_p.add_argument("--from-results", action="store_true",
                       help="Skip execution; load pre-run CSVs from results/ and generate insights")
    run_p.add_argument("--results-dir", default="results", help="Directory containing pre-run CSVs (used with --from-results)")
    run_p.add_argument("--max-review-iterations", type=int, default=3)

    # profiler extract
    ext_p = sub.add_parser("extract", help="Extraction + validation only")
    ext_p.add_argument("--input", required=True, help="Path to intake text file")
    ext_p.add_argument("--harness", action="store_true")

    # profiler introspect
    isp_p = sub.add_parser("introspect", help="Print schema metadata + depth-1 discovery")
    isp_p.add_argument("--config", required=True, help="Path to configs/{entity}.json")
    isp_p.add_argument("--harness", action="store_true")

    # profiler run-sql
    rsql_p = sub.add_parser("run-sql", help="Execute a profiling SQL file against Snowflake and save CSVs")
    rsql_p.add_argument("--sql", default="sql/customer_profiling.sql", help="Path to .sql file")
    rsql_p.add_argument("--out", default="results", help="Output directory for CSV files")

    args = parser.parse_args()

    from_results = getattr(args, "from_results", False)
    settings = Settings(
        # from_results implies harness for all stub stages; executor reads CSVs instead
        harness=getattr(args, "harness", False) or getattr(args, "generate_sql", False) or from_results,
        generate_sql=getattr(args, "generate_sql", False),
        from_results=from_results,
        max_review_iterations=getattr(args, "max_review_iterations", 3),
        results_dir=getattr(args, "results_dir", "results"),
    )

    if args.command == "run":
        if args.plan_only:
            print("--plan-only mode: implemented in Phase 6")
            sys.exit(0)
        run(args.input, settings)

    elif args.command == "extract":
        _cmd_extract(args.input, settings)

    elif args.command == "introspect":
        _cmd_introspect(args.config, settings)

    elif args.command == "run-sql":
        _cmd_run_sql(args.sql, args.out)


def _cmd_extract(input_path: str, settings: Settings) -> None:
    from .extractor import extract_entity_config
    from .intake_reader import read_intake
    from .introspection import get_schema_metadata
    from .validation import validate_config

    raw_text = read_intake(input_path)
    config, clarifications = extract_entity_config(raw_text, settings)
    if clarifications:
        print("Clarification questions:\n")
        for i, q in enumerate(clarifications, 1):
            print(f"  {i}. {q}")
        sys.exit(1)

    schema_meta = get_schema_metadata(config, settings)
    config, questions = validate_config(config, schema_meta, settings)
    if questions:
        print("Validation questions:\n")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")
        sys.exit(1)

    print(f"EntityConfig validated and saved to configs/{config.entity.lower()}.json")


def _cmd_introspect(config_path: str, settings: Settings) -> None:
    import json
    from pathlib import Path
    from .models import EntityConfig
    from .introspection import get_schema_metadata
    from .discovery import run_discovery

    config = EntityConfig.model_validate_json(Path(config_path).read_text(encoding="utf-8-sig"))
    schema_meta = get_schema_metadata(config, settings)
    print("Schema metadata:")
    for tm in schema_meta:
        print(f"  {tm.table} ({tm.row_count} rows, {len(tm.columns)} columns)")

    discovered = run_discovery(config, settings)
    print("\nDepth-1 discovered tables:")
    for dt in discovered:
        print(f"  {dt.fqn}  via {dt.matched_column}  [{dt.link_basis}]  rows={dt.row_count}")


def _cmd_run_sql(sql_path: str, out_dir: str) -> None:
    from .query_runner import run_sql_file
    written = run_sql_file(sql_path, out_dir)
    print(f"\nDone. {len(written)} CSV file(s) written to {out_dir}/")


if __name__ == "__main__":
    main()
