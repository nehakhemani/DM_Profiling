from __future__ import annotations

import json
import os
import re

from .config import Settings
from .models import EntityConfig, Finding, InsightReport, MetricResult, ProfilingPlan, ReviewFeedback

# ── Provider detection ────────────────────────────────────────────────────────

def _detect_provider() -> str:
    """
    Returns the active LLM provider based on environment variables.
    Priority: LLM_PROVIDER env var > key presence > rule_based fallback.
    """
    explicit = os.environ.get("LLM_PROVIDER", "auto").strip().lower()
    if explicit != "auto":
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "groq"
    if os.environ.get("OLLAMA_HOST", "").strip() or _ollama_running():
        return "ollama"
    return "rule_based"


def _ollama_running() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434", timeout=1)
        return True
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def generate_insights(
    config: EntityConfig,
    results: list[MetricResult],
    settings: Settings,
    previous_report: InsightReport | None = None,
    feedback: ReviewFeedback | None = None,
) -> InsightReport:
    """
    Dispatch order: harness fixture → LLM (anthropic/groq/ollama) → rule_based.
    LLM provider is auto-detected from environment keys or LLM_PROVIDER env var.
    """
    if settings.harness and not settings.from_results:
        raw = json.loads(settings.fixture_path("insight_report.json").read_text(encoding="utf-8-sig"))
        return InsightReport.model_validate(raw)

    provider = _detect_provider()
    print(f"  [insights] provider={provider}")

    if provider != "rule_based":
        is_revision = previous_report is not None and feedback is not None
        prompt = _revision_prompt(config, results, previous_report, feedback) if is_revision \
                 else _initial_prompt(config, results)
        for attempt in range(2):
            text = _complete(provider, prompt)
            try:
                return InsightReport.model_validate(llm_extract_json(text))
            except Exception as exc:
                if attempt == 1:
                    print(f"  [insights] LLM parse failed ({exc}), falling back to rule_based")

    return _rule_based_insights(config, results)


def review_report(
    config: EntityConfig,
    plan: ProfilingPlan,
    results: list[MetricResult],
    report: InsightReport,
    settings: Settings,
) -> ReviewFeedback:
    """
    Dispatch order: harness fixture → LLM review → auto-approve (rule_based).
    """
    if settings.harness and not settings.from_results:
        raw = json.loads(settings.fixture_path("review_feedback.json").read_text(encoding="utf-8-sig"))
        return ReviewFeedback.model_validate(raw)

    provider = _detect_provider()

    if provider != "rule_based":
        prompt = _review_prompt(config, plan, results, report)
        for attempt in range(2):
            text = _complete(provider, prompt)
            try:
                fb = ReviewFeedback.model_validate(llm_extract_json(text))
                if fb.approved and fb.feedback:
                    if attempt == 1:
                        break   # contract violation after retry → fall through to auto-approve
                    continue
                return fb
            except Exception:
                if attempt == 1:
                    break

    return ReviewFeedback(approved=True, feedback=[])


# ── Rule-based insight generator ──────────────────────────────────────────────

def _rule_based_insights(config: EntityConfig, results: list[MetricResult]) -> InsightReport:
    null_metrics    = [r for r in results if r.metric == "null_rate"]
    overlap_metrics = [r for r in results if r.metric == "cross_system_overlap"]
    join_metrics    = [r for r in results if r.metric == "match_rate"]
    dist_metrics    = [r for r in results if r.metric == "top_values"]
    crosstab_metrics = [r for r in results if r.metric == "segment_cross_tab"]

    findings: list[Finding] = []

    # 1. Null analysis — skip perfectly-populated columns (0% null)
    for m in sorted(null_metrics, key=lambda x: -(float(x.value or 0))):
        rate = float(m.value or 0)
        if rate == 0.0:
            continue
        total     = m.detail.get("total_rows") or 0
        non_nulls = m.detail.get("non_nulls") or 0
        null_count = total - non_nulls if total else None
        pct        = f"{rate * 100:.2f}%"
        abs_clause = f" ({null_count:,} of {total:,} records)" if null_count else ""
        tbl        = m.table.split(".")[-1]
        col        = m.column

        if rate > 0.20:
            sev = "high"
            rec = (f"Investigate source population rules for {col} in {tbl}. "
                   f"Agree on a default or backfill strategy before CRM migration; "
                   f"segment analysis will be unreliable until this field is populated.")
        elif rate > 0.05:
            sev = "medium"
            rec = (f"Determine whether nulls in {col} represent a known data gap or a "
                   f"source system issue. Prioritise backfill for active customer records.")
        else:
            sev = "low"
            rec = (f"Volume is small — confirm whether the {null_count:,} null records "
                   f"are inactive or legacy entries and exclude them from migration if so.")

        findings.append(Finding(
            severity=sev,
            column=col,
            finding=f"{pct} null rate on {col} in {tbl}{abs_clause}.",
            recommendation=rec,
        ))

    # 2. Cross-system overlap
    for m in overlap_metrics:
        d          = m.detail
        left       = d.get("left_keys") or 0
        right      = d.get("right_keys") or 0
        in_both    = d.get("in_both") or 0
        left_only  = d.get("left_only") or 0
        right_only = d.get("right_only") or 0
        rate       = float(m.value or 0)
        pct        = f"{rate * 100:.3f}%"
        sev        = "high" if rate < 0.10 else "medium"

        findings.append(Finding(
            severity=sev,
            column=None,
            finding=(
                f"Cross-system overlap: {in_both:,} of {left:,} Siebel records ({pct}) "
                f"match a Salesforce account via the cross-system key. "
                f"{left_only:,} records exist only in Siebel; {right_only:,} exist only in Salesforce."
            ),
            recommendation=(
                "The volume mismatch (Siebel 21M vs Salesforce ~1.9K) suggests these systems "
                "serve fundamentally different scopes. Define separate migration subsets: "
                "matched records, Siebel-only, and Salesforce-only — each with distinct handling rules."
            ),
        ))

    # 3. Join / depth-1 coverage
    for m in join_metrics:
        d          = m.detail
        total      = d.get("total_records") or 0
        matched    = d.get("matched_records") or 0
        rate       = float(m.value or 0)
        join_tbl   = (d.get("join_table") or "related table").split(".")[-1]
        join_key   = d.get("join_key") or "key"
        base_tbl   = m.table.split(".")[-1]

        if rate == 0.0:
            findings.append(Finding(
                severity="high",
                column=None,
                finding=(
                    f"0% join coverage from {base_tbl} to {join_tbl} via {join_key}: "
                    f"none of the {total:,} base records produced a match."
                ),
                recommendation=(
                    f"Verify that {join_key} is the correct join key for this relationship. "
                    f"The tables may link via a different column, or {join_tbl} may use a "
                    f"surrogate key that does not align with {base_tbl}.{join_key}."
                ),
            ))
        elif rate >= 0.80:
            unmatched = total - matched
            findings.append(Finding(
                severity="low",
                column=None,
                finding=(
                    f"{rate * 100:.0f}% join coverage from {base_tbl} to {join_tbl} "
                    f"via {join_key} ({matched:,} of {total:,} records matched; "
                    f"{unmatched:,} unmatched)."
                ),
                recommendation=(
                    f"Review the {unmatched:,} unmatched {base_tbl} records — "
                    "these may be accounts without linked contacts, test records, "
                    "or defunct entities. Confirm exclusion criteria before migration."
                ),
            ))
        else:
            findings.append(Finding(
                severity="medium",
                column=None,
                finding=(
                    f"{rate * 100:.0f}% join coverage from {base_tbl} to {join_tbl} "
                    f"via {join_key} ({matched:,} of {total:,} records matched)."
                ),
                recommendation="Investigate the unmatched population before migration.",
            ))

    # 4. Segment distributions — de-duplicate (distribution_analysis and segment_distribution
    #    both produce top_values for the same columns; keep one per table+column)
    seen: set[tuple] = set()
    for m in dist_metrics:
        key = (m.table, m.column)
        if key in seen:
            continue
        seen.add(key)

        values = m.detail.get("values") or []
        if not values:
            continue

        tbl    = m.table.split(".")[-1]
        col    = m.column
        n_vals = len(values)
        top    = values[0]
        top_v  = top.get("value")
        top_f  = top.get("frequency") or 0

        # Detect blank/null in distribution
        null_entry = next(
            (v for v in values if v.get("value") is None or v.get("value") == ""), None
        )
        null_clause = (
            f" {null_entry['frequency']:,} records have a null/blank value."
            if null_entry else ""
        )
        sev = "medium" if null_entry and (null_entry.get("frequency") or 0) > 0 else "low"

        findings.append(Finding(
            severity=sev,
            column=col,
            finding=(
                f"{col} in {tbl} has {n_vals} distinct value(s); "
                f"top value is '{top_v}' ({top_f:,} records).{null_clause}"
            ),
            recommendation=(
                f"Validate the full value set of {col} with business stakeholders "
                "to confirm the segment taxonomy is complete. "
                "Map blank/null values to a default before migration."
            ),
        ))

    # 5. Segment cross-tabs
    for m in crosstab_metrics:
        d         = m.detail
        left_col  = d.get("left_col") or "left_segment"
        right_col = d.get("right_col") or "right_segment"
        rows      = d.get("rows") or []
        if not rows:
            continue
        top = rows[0]
        findings.append(Finding(
            severity="low",
            column=None,
            finding=(
                f"Segment cross-tab ({left_col} × {right_col}): "
                f"{len(rows)} combination(s) found. "
                f"Dominant mapping: '{top.get('left_segment')}' → "
                f"'{top.get('right_segment')}' ({top.get('frequency', 0):,} records)."
            ),
            recommendation=(
                f"Use this cross-tab to define the canonical segment mapping between systems "
                f"during CRM consolidation. Validate dominant mappings ({left_col} → "
                f"{right_col}) with business stakeholders before applying them in migration ETL."
            ),
        ))

    # Sort high → medium → low
    _order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: _order[f.severity])

    summary = _build_summary(null_metrics, overlap_metrics, join_metrics, findings, config)
    return InsightReport(summary=summary, findings=findings)


def _build_summary(
    null_metrics: list[MetricResult],
    overlap_metrics: list[MetricResult],
    join_metrics: list[MetricResult],
    findings: list[Finding],
    config: EntityConfig,
) -> str:
    parts: list[str] = []

    # Scale facts
    siebel_row = next(
        (m for m in null_metrics if "s_org_ext" in m.table and m.column == "row_id"), None
    )
    sf_row = next(
        (m for m in null_metrics if "account" in m.table and m.column == "Id"), None
    )
    if siebel_row and sf_row:
        s_total = siebel_row.detail.get("total_rows") or 0
        sf_total = sf_row.detail.get("total_rows") or 0
        parts.append(
            f"The {config.entity} entity spans {s_total:,} Siebel records "
            f"and {sf_total:,} Salesforce accounts — a {s_total // max(sf_total, 1):,}× "
            f"volume difference indicating the two systems serve different scopes."
        )

    # Overlap fact
    if overlap_metrics:
        om  = overlap_metrics[0]
        d   = om.detail
        pct = f"{float(om.value or 0) * 100:.3f}%"
        parts.append(
            f"Cross-system key linkage is critically low: only "
            f"{d.get('in_both', 0):,} records match across both systems ({pct}), "
            f"leaving {d.get('left_only', 0):,} Siebel-only and "
            f"{d.get('right_only', 0):,} Salesforce-only records unresolved."
        )

    # Severity summary
    high_n = sum(1 for f in findings if f.severity == "high")
    med_n  = sum(1 for f in findings if f.severity == "medium")
    if high_n or med_n:
        parts.append(
            f"There are {high_n} high-severity and {med_n} medium-severity "
            f"finding(s) that must be addressed before CRM consolidation can proceed."
        )

    return " ".join(parts)


# ── LLM dispatch ─────────────────────────────────────────────────────────────

def _complete(provider: str, prompt: str) -> str:
    if provider == "anthropic":
        return _complete_anthropic(prompt)
    if provider == "groq":
        return _complete_groq(prompt)
    if provider == "ollama":
        return _complete_ollama(prompt)
    raise ValueError(f"Unknown LLM provider: {provider}")


def _complete_anthropic(prompt: str) -> str:
    import anthropic
    return anthropic.Anthropic().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text


def _complete_groq(prompt: str) -> str:
    from groq import Groq
    # llama-3.1-70b-versatile is the best free model on Groq for structured JSON
    model = os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile")
    return Groq().chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ).choices[0].message.content


def _complete_ollama(prompt: str) -> str:
    import urllib.request, json as _json
    host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    body  = _json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req   = urllib.request.Request(f"{host}/api/generate", data=body,
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return _json.loads(resp.read())["response"]


# ── Shared JSON helper (also used by reviewer.py) ────────────────────────────

def llm_complete(prompt: str) -> str:
    return _complete(_detect_provider(), prompt)


def llm_extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        return json.loads(m.group(1))
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start:end])


# ── Prompts (LLM mode only) ───────────────────────────────────────────────────

def _initial_prompt(config: EntityConfig, results: list[MetricResult]) -> str:
    rules  = "\n".join(f"  {i+1}. {r.rule}" for i, r in enumerate(config.profiling_rules))
    tables = "\n".join(f"  - {t.fqn} (system: {t.system}, key: {t.record_key})"
                       for t in config.tables)
    return f"""You are a senior data quality analyst performing a structured profiling assessment.

Entity: {config.entity}
Purpose: {config.purpose}

Source tables:
{tables}

Profiling rules:
{rules}

Metric results (real Snowflake data):
{json.dumps([m.model_dump() for m in results], indent=2)}

Produce an InsightReport as JSON:
{{"summary": "...", "findings": [{{"severity": "high|medium|low", "column": "...|null", "finding": "...", "recommendation": "..."}}]}}

Rules: cite actual numbers; high=>null_rate>20% or overlap<10% or match_rate=0; order high→medium→low; return ONLY JSON."""


def _revision_prompt(
    config: EntityConfig, results: list[MetricResult],
    previous_report: InsightReport, feedback: ReviewFeedback,
) -> str:
    items = "\n".join(
        f"  [{fb.dimension}] {fb.issue} — Required: {fb.required_change}"
        for fb in feedback.feedback
    )
    return f"""Revise this InsightReport addressing all feedback.

Entity: {config.entity}
Feedback:
{items}

Previous report:
{previous_report.model_dump_json(indent=2)}

Metric results:
{json.dumps([m.model_dump() for m in results], indent=2)}

Return revised InsightReport JSON only."""


def _review_prompt(
    config: EntityConfig, plan: ProfilingPlan,
    results: list[MetricResult], report: InsightReport,
) -> str:
    rules = "\n".join(f"  {i+1}. {r.rule}" for i, r in enumerate(config.profiling_rules))
    return f"""Review this InsightReport on five dimensions.

Entity: {config.entity} | Purpose: {config.purpose}
Rules: {rules}

Metrics: {json.dumps([m.model_dump() for m in results], indent=2)}
Report: {report.model_dump_json(indent=2)}

Dimensions: intent_alignment, plan_coverage, grounding, severity_calibration, actionability.
Return: {{"approved": true|false, "feedback": [{{"dimension": "...", "issue": "...", "required_change": "..."}}]}}
approved=true requires feedback=[]. Return ONLY JSON."""
