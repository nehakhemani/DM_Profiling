from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# --- §4.1 EntityConfig ---

class SourceTable(BaseModel):
    fqn: str
    system: str
    record_key: str


class CrossSystemMatch(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str


class ProfilingRule(BaseModel):
    rule: str
    fields: list[str] = []


class EntityConfig(BaseModel):
    entity: str
    purpose: str
    tables: list[SourceTable]
    cross_system_matches: list[CrossSystemMatch] = []
    profiling_rules: list[ProfilingRule]
    discovery_depth: int = 1


# --- §4.2 SchemaMetadata ---

class ColumnMeta(BaseModel):
    table: str
    column: str
    data_type: str
    is_nullable: bool


class TableMeta(BaseModel):
    table: str
    row_count: int | None
    columns: list[ColumnMeta]


# --- §4.3 ProfilingTask / ProfilingPlan ---

TaskType = Literal[
    "null_analysis",
    "distinct_count",
    "uniqueness_check",
    "pattern_analysis",
    "distribution_analysis",
    "join_analysis",
    "cross_system_overlap",
    "segment_variation",
]


class ProfilingTask(BaseModel):
    type: TaskType
    table: str | None = None
    columns: list[str] = []
    join_table: str | None = None
    join_key: str | None = None
    match: CrossSystemMatch | None = None
    segment_columns: dict[str, list[str]] = {}
    business_reason: str


class ProfilingPlan(BaseModel):
    profiling_tasks: list[ProfilingTask]


# --- §4.4 MetricResult ---

class MetricResult(BaseModel):
    entity: str
    table: str
    column: str | None
    metric: str
    value: float | int | str
    detail: dict = {}


# --- §4.5 InsightReport ---

class Finding(BaseModel):
    severity: Literal["high", "medium", "low"]
    column: str | None
    finding: str
    recommendation: str


class InsightReport(BaseModel):
    summary: str
    findings: list[Finding]


# --- §4.6 ReviewFeedback / ReviewedReport ---

ReviewDimension = Literal[
    "intent_alignment",
    "plan_coverage",
    "grounding",
    "severity_calibration",
    "actionability",
]


class FeedbackItem(BaseModel):
    dimension: ReviewDimension
    issue: str
    required_change: str


class ReviewFeedback(BaseModel):
    approved: bool
    feedback: list[FeedbackItem]


class ReviewedReport(BaseModel):
    report: InsightReport
    review_status: Literal["approved", "max_iterations_reached"]
    iterations: int
    review_history: list[ReviewFeedback]


# --- §5.3 DiscoveredTable ---

class DiscoveredTable(BaseModel):
    fqn: str
    matched_column: str
    row_count: int | None
    link_basis: Literal["name_match", "constraint"]
