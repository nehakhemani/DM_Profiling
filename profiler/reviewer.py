from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .insights import generate_insights
from .models import (
    EntityConfig,
    InsightReport,
    MetricResult,
    ProfilingPlan,
    ReviewFeedback,
    ReviewedReport,
)


def review_report(
    config: EntityConfig,
    plan: ProfilingPlan,
    results: list[MetricResult],
    report: InsightReport,
    settings: Settings,
) -> ReviewFeedback:
    """
    Single review call against the §5.9 five-dimension rubric.

    Harness: loads tests/fixtures/review_feedback.json.
    Real (Phase 8): calls LLM at temperature=0; validates against ReviewFeedback;
    treats approved=true with non-empty feedback as a parse failure and retries once.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("review_feedback.json").read_text(encoding="utf-8"))
        return ReviewFeedback.model_validate(raw)

    raise NotImplementedError("Live reviewer not yet implemented — use --harness")


def run_review_loop(
    config: EntityConfig,
    plan: ProfilingPlan,
    results: list[MetricResult],
    settings: Settings,
    run_id: str,
) -> ReviewedReport:
    """
    Orchestrates the generate → review → revise loop (§5.9).

    This is the final loop logic — it is not replaced in later phases;
    only generate_insights and review_report are replaced.
    """
    run_dir = settings.run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)

    history: list[ReviewFeedback] = []
    report = generate_insights(config, results, settings)

    for i in range(1, settings.max_review_iterations + 1):
        feedback = review_report(config, plan, results, report, settings)

        # Contract enforcement: approved=true must have empty feedback
        if feedback.approved and feedback.feedback:
            feedback = ReviewFeedback(approved=False, feedback=feedback.feedback)

        _persist(run_dir / f"review_{i}.json", feedback.model_dump_json(indent=2))
        history.append(feedback)

        if feedback.approved:
            return ReviewedReport(
                report=report,
                review_status="approved",
                iterations=i,
                review_history=history,
            )

        report = generate_insights(config, results, settings, previous_report=report, feedback=feedback)

    return ReviewedReport(
        report=report,
        review_status="max_iterations_reached",
        iterations=settings.max_review_iterations,
        review_history=history,
    )


def _persist(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
