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
    Pure transformation: (task execution records, entity name) -> MetricResult list.

    Harness: loads tests/fixtures/metric_results.json.
    Real (Phase 3): maps each task type's raw rows to MetricResult records per §5.7.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("metric_results.json").read_text(encoding="utf-8-sig"))
        return [MetricResult.model_validate(r) for r in raw]

    raise NotImplementedError("Live normalizer not yet implemented — use --harness")
