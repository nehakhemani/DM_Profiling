from __future__ import annotations

import argparse
import sys

from .config import Settings
from .pipeline import run


def main() -> None:
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
    run_p.add_argument("--max-review-iterations", type=int, default=3)

    # profiler extract
    ext_p = sub.add_parser("extract", help="Extraction + validation only")
    ext_p.add_argument("--input", required=True, help="Path to intake text file")
    ext_p.add_argument("--harness", action="store_true")

    # profiler introspect
    isp_p = sub.add_parser("introspect", help="Print schema metadata + depth-1 discovery")
    isp_p.add_argument("--config", required=True, help="Path to configs/{entity}.json")
    isp_p.add_argument("--harness", action="store_true")

    args = parser.parse_args()

    settings = Settings(
        harness=getattr(args, "harness", False) or getattr(args, "generate_sql", False),
        generate_sql=getattr(args, "generate_sql", False),
        max_review_iterations=getattr(args, "max_review_iterations", 3),
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


if __name__ == "__main__":
    main()
