from __future__ import annotations

import json

from .config import Settings
from .models import EntityConfig, InsightReport, MetricResult, ReviewFeedback


def generate_insights(
    config: EntityConfig,
    results: list[MetricResult],
    settings: Settings,
    previous_report: InsightReport | None = None,
    feedback: ReviewFeedback | None = None,
) -> InsightReport:
    """
    Produces an InsightReport from profiling results.

    On initial pass: uses the §5.8 initial-pass prompt.
    On revision passes: uses the revision prompt, including previous_report and feedback.

    Harness: loads tests/fixtures/insight_report.json (same fixture for all passes).
    Real (Phase 8): calls LLM at temperature=0; validates against InsightReport;
    retries once on parse failure.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("insight_report.json").read_text(encoding="utf-8"))
        return InsightReport.model_validate(raw)

    raise NotImplementedError("Live insight generator not yet implemented — use --harness")
