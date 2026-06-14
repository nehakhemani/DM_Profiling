from __future__ import annotations

import json

from .config import Settings
from .models import MetricResult


def normalize_results(
    raw_results: list[dict],
    entity: str,
    settings: Settings,
) -> list[MetricResult]:
    """
    Converts executor output into MetricResult records.

    Harness: loads tests/fixtures/metric_results.json (ignores raw_results).
    Real: maps each block's CSV rows to MetricResult(s) based on block_kind.
    """
    if settings.harness and not settings.from_results:
        raw = json.loads(settings.fixture_path("metric_results.json").read_text(encoding="utf-8-sig"))
        return [MetricResult.model_validate(r) for r in raw]

    metrics: list[MetricResult] = []
    for result in raw_results:
        for block in result.get("blocks", []):
            if block.get("status") != "success" or not block.get("rows"):
                continue
            m = _block_to_metric(block, entity)
            if m is not None:
                metrics.append(m)
    return metrics


# ── Block → MetricResult ──────────────────────────────────────────────────────

def _block_to_metric(block: dict, entity: str) -> MetricResult | None:
    kind = block["block_kind"]
    table = block.get("table", "")
    column = block.get("column")
    rows = block["rows"]

    if kind == "null_analysis":
        row = rows[0]
        return MetricResult(
            entity=entity, table=table, column=column,
            metric="null_rate",
            value=_f(row.get("null_rate", 0.0)),
            detail={"total_rows": row.get("total_rows"), "non_nulls": row.get("non_nulls")},
        )

    if kind in ("distribution_analysis", "segment_distribution"):
        top = [{"value": r.get("value"), "frequency": r.get("frequency")} for r in rows]
        return MetricResult(
            entity=entity, table=table, column=column,
            metric="top_values",
            value=len(top),
            detail={"values": top},
        )

    if kind == "segment_crosstab":
        crosstab = [
            {"left_segment": r.get("left_segment"), "right_segment": r.get("right_segment"),
             "frequency": r.get("frequency")}
            for r in rows
        ]
        return MetricResult(
            entity=entity, table=table, column=None,
            metric="segment_cross_tab",
            value=len(crosstab),
            detail={
                "left_col": block.get("left_col"),
                "right_col": block.get("right_col"),
                "rows": crosstab,
            },
        )

    if kind == "cross_system_overlap":
        row = rows[0]
        left = row.get("left_keys") or 0
        in_both = row.get("in_both") or 0
        overlap_rate = round(in_both / left, 6) if left else 0.0
        return MetricResult(
            entity=entity, table=table, column=None,
            metric="cross_system_overlap",
            value=overlap_rate,
            detail={
                "left_keys": left,
                "right_keys": row.get("right_keys"),
                "in_both": in_both,
                "left_only": row.get("left_only"),
                "right_only": row.get("right_only"),
            },
        )

    if kind == "join_analysis":
        row = rows[0]
        return MetricResult(
            entity=entity, table=table, column=None,
            metric="match_rate",
            value=_f(row.get("match_rate", 0.0)),
            detail={
                "join_table": block.get("join_table"),
                "join_key": block.get("join_key"),
                "total_records": row.get("total_records"),
                "matched_records": row.get("matched_records"),
            },
        )

    return None


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
