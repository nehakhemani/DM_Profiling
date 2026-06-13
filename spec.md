# BUILD SPEC — AI Data Profiling Agent for Snowflake

> **Instructions to the coding agent:** Implement this system exactly as specified. Follow the build order in Section 10. Do not deviate from the architecture, do not add features beyond the checklist, and respect every rule in Section 9 (MUST NOT). Ask before making any design decision not covered here.

---

## 1. What you are building

A Python application that converts plain-language business input into executable Snowflake data discovery and profiling analysis, delivering structured insights AND a visual dashboard.

**Input is plain/simple text.** The user describes the entity, its tables, keys, and profiling rules in ordinary language (free text or a lightweight labeled template — see §2). The system extracts a structured, schema-validated config from that text. The user never writes JSON.

**Example interaction (this is also the v1 feasibility test case, verbatim):**

User input (plain text):
> Data discovery and profiling for Customer entity. Base tables: spark_ods.siebel.s_org_ext (system: Siebel) and spark_ods.salesforce_reports.accounts (system: Salesforce). Relationship between the two: ou_num in the Siebel table = Customer_Number__c in the Salesforce table. row_id in Siebel and Id in Salesforce are the relationship keys to other tables within their respective systems. Profiling rules: 1) look for all variations on customer segment — identified by record type in Salesforce, and market_class_cd and market_type_cd in Siebel; 2) customers which are present in both systems.

System output:
- Depth-1 discovery: related tables linked to the base tables via their record keys
- Profiling results: null/missing-important-data analysis, related-entity (join) analysis, segment variation across both systems, cross-system customer overlap
- Structured insight report (review-loop approved) + a self-contained HTML dashboard

**Build approach: harness first.** Phase 0 builds an end-to-end pipeline skeleton with every stage stubbed (mocked LLMs, fixture schema, canned results) that already produces a report and dashboard from canned data. Real implementations then replace stubs one phase at a time. The templated structure — intake template, config schema, SQL templates, report and dashboard layout — IS the harness.

**Tech stack:**
- Python 3.11+
- `snowflake-connector-python` for execution
- `pydantic` v2 for internal data models and LLM output validation
- `anthropic` SDK for the four LLM steps (extractor, planner, insight generator, reviewer)
- `plotly` for the self-contained HTML dashboard
- `pytest` for tests
- No web framework in v1 — CLI entry point only (`python -m profiler run --input intake/customer.txt`)

---

## 2. Business input: plain-text intake and automated grooming (start here)

The user provides everything in plain, simple text — no JSON, no forms. Two input shapes are supported, and both go through the same extraction step. It is fine to provide everything in one template or split across several files; the extractor merges them.

**Shape A — free text:** exactly as a stakeholder would write it. The §1 example paragraph is valid input as-is.

**Shape B — lightweight labeled template** (same information, easier to keep complete). One text file per entity at `intake/{entity}.txt`:

```
ENTITY: Customer
PURPOSE: Data discovery and profiling for the customer entity (CRM consolidation)

TABLES:
- spark_ods.siebel.s_org_ext | system: Siebel | record key: row_id
- spark_ods.salesforce_reports.accounts | system: Salesforce | record key: Id

CROSS-SYSTEM MATCH:
- s_org_ext.ou_num = accounts.Customer_Number__c

PROFILING RULES (plain language, one per line):
1. Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
2. Customers which are present in both systems
3. Missing important data on key fields

DISCOVERY: depth 1 (find related tables linked to the base tables via their record keys)
```

### 2.1 Automated grooming (extract → validate → clarify → map)

Grooming is automated by the system, not a manual workshop:

1. **Extract** — the LLM Context Extractor (§5.1) parses the plain text into an `EntityConfig` draft. It copies table and column names exactly as written and never invents names.
2. **Validate** — every table and column is checked against live INFORMATION_SCHEMA (§5.2). A mismatch becomes a specific question (e.g., "`market_type_cd` not found in spark_ods.siebel.s_org_ext — closest column: MARKET_TYPE_CD. Use that?").
3. **Clarify** — extraction gaps and validation mismatches are printed as a numbered question list and the run stops. The user edits the intake text and reruns. v1 is non-interactive: print questions, exit, rerun.
4. **Map** — each profiling rule is matched to task types using §2.2. A rule that maps to nothing is reported back as out-of-scope — never improvised.

### 2.2 Plain-language rule → task type mapping (grooming aid)

| User says (plain language) | Maps to task type |
|---|---|
| "missing / incomplete / blank / missing important data" | `null_analysis` |
| "are these unique? / we suspect duplicates" | `uniqueness_check`, `distinct_count` |
| "formats are inconsistent" (email, phone, codes) | `pattern_analysis` |
| "all variations on X / fragmented values / segment variations" | `distribution_analysis`, `segment_variation` |
| "related tables / linked entities / what else is connected" | discovery (depth 1) + `join_analysis` |
| "records present in both systems / overlap / matched across systems" | `cross_system_overlap` |

### 2.3 Definition of Ready (auto-checked before any run)

The system blocks execution and prints questions until ALL of these hold:

- [ ] Entity name and purpose extracted
- [ ] ≥ 1 base table, each with a fully qualified name (DATABASE.SCHEMA.TABLE), a system label, and a record key
- [ ] All tables, record keys, match columns, and rule fields verified to exist via introspection
- [ ] Cross-system match columns verified on both sides (when 2+ systems are involved)
- [ ] Every profiling rule mapped to ≥ 1 task type, or explicitly reported back as out-of-scope
- [ ] Discovery depth set (default 1)

**Traceability chain:** the user's plain-text rule → `profiling_rules[].rule` (verbatim) → mapped task's `business_reason` → insight finding → review dimension `intent_alignment`. The user's original words are carried through the pipeline and enforced end-to-end.

---

## 3. Architecture (do not change this)

```
[1. Plain-Text Business Input (free text or intake template)]
        ↓
[2. LLM Context Extractor — parses text into an EntityConfig draft]
        ↓
[3. Schema Validation + Clarification Gate — verify against Snowflake;
    print questions and stop if the Definition of Ready fails]
        ↓
[4. Discovery (depth 1) — find related tables via record keys (deterministic, metadata-only)]
        ↓
[5. LLM Planner — outputs a JSON profiling plan (WHAT to analyze)]
        ↓
[6. SQL Generator — deterministic templates, NO LLM]
        ↓
[7. Snowflake Executor — batch execution]
        ↓
[8. Result Normalizer — flattens results into a uniform metric format]
        ↓
[9. LLM Insight Generator — interprets results (WHY it matters)]
        ↓
[10. LLM Review Agent — critiques the insight report]
        ↕  (revision loop: feedback → regenerate insights → re-review,
            until approved or max_review_iterations reached)
        ↓
[11. Final Report + Visualization Dashboard (deterministic HTML)]
```

**Core design rule:** there are exactly **four** AI steps — extraction (step 2), planning (step 5), interpretation (step 9), and review (step 10). Everything else is deterministic, template-driven code. No LLM ever writes or sees SQL. The extractor converts language into structure and never touches the database. Discovery and visualization are fully deterministic. The review loop operates only on the insight report and the normalized results — it can never trigger new queries or modify the plan.

---

## 4. Data models (Pydantic schemas — define these first)

### 4.1 `EntityConfig` (extracted from plain text, then schema-validated)

```python
class SourceTable(BaseModel):
    fqn: str                  # fully qualified: DATABASE.SCHEMA.TABLE
    system: str               # e.g. "Siebel", "Salesforce"
    record_key: str           # key linking this table to other tables WITHIN its system

class CrossSystemMatch(BaseModel):
    left_table: str           # fqn
    left_column: str
    right_table: str          # fqn
    right_column: str

class ProfilingRule(BaseModel):
    rule: str                 # the user's plain-language rule, VERBATIM
    fields: list[str] = []    # resolved "FQN.COLUMN" references where the rule names fields

class EntityConfig(BaseModel):
    entity: str
    purpose: str
    tables: list[SourceTable]
    cross_system_matches: list[CrossSystemMatch] = []
    profiling_rules: list[ProfilingRule]
    discovery_depth: int = 1
```

The user never writes this JSON — it is produced by the extractor (§5.1), validated (§5.2), and saved to `configs/{entity}.json` for reuse and audit. The v1 feasibility config is the Customer (Siebel + Salesforce) case, extracted from the §1 input. No entity, table, or column names may appear anywhere in code.

### 4.2 `SchemaMetadata` (built by introspection)

```python
class ColumnMeta(BaseModel):
    table: str
    column: str
    data_type: str
    is_nullable: bool

class TableMeta(BaseModel):
    table: str
    row_count: int | None
    columns: list[ColumnMeta]
```

### 4.3 `ProfilingTask` (planner output)

```python
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
    table: str | None = None              # fqn; None for cross-system task types
    columns: list[str] = []
    join_table: str | None = None         # only for join_analysis
    join_key: str | None = None           # only for join_analysis
    match: CrossSystemMatch | None = None # only for cross_system_overlap / segment_variation
    segment_columns: dict[str, list[str]] = {}  # fqn -> segment columns; only for segment_variation
    business_reason: str                  # must trace back to a profiling_rules[].rule

class ProfilingPlan(BaseModel):
    profiling_tasks: list[ProfilingTask]
```

### 4.4 `MetricResult` (normalizer output — feeds the insight LLM)

```python
class MetricResult(BaseModel):
    entity: str
    table: str
    column: str | None
    metric: str          # e.g. "null_rate", "distinct_count", "match_rate"
    value: float | int | str
    detail: dict = {}    # e.g. top patterns with frequencies
```

### 4.5 `InsightReport` (insight generator output)

```python
class Finding(BaseModel):
    severity: Literal["high", "medium", "low"]
    column: str | None
    finding: str
    recommendation: str

class InsightReport(BaseModel):
    summary: str
    findings: list[Finding]
```

### 4.6 `ReviewFeedback` (review agent output)

```python
ReviewDimension = Literal[
    "intent_alignment",      # does the report answer the user's business request?
    "plan_coverage",         # does it address all significant profiling tasks that ran?
    "grounding",             # is every claim traceable to a computed MetricResult?
    "severity_calibration",  # are high/medium/low ratings justified by the numbers?
    "actionability",         # are recommendations concrete and business-relevant?
]

class FeedbackItem(BaseModel):
    dimension: ReviewDimension
    issue: str             # what is wrong, citing the specific finding or metric
    required_change: str   # what the insight generator must do differently

class ReviewFeedback(BaseModel):
    approved: bool         # True ⇒ feedback must be empty
    feedback: list[FeedbackItem]

class ReviewedReport(BaseModel):
    report: InsightReport
    review_status: Literal["approved", "max_iterations_reached"]
    iterations: int
    review_history: list[ReviewFeedback]
```

---

## 5. Component specifications

### 5.1 LLM Context Extractor

Converts the plain-text intake into an `EntityConfig` draft. Call with `temperature=0`. Prompts verbatim:

**System prompt:**

```
You are a Data Profiling Intake Extractor.

You convert plain-language descriptions of data entities into a structured JSON config.

RULES:
- Output ONLY valid JSON — no prose, no markdown fences
- Copy table and column names EXACTLY as written by the user. Never invent,
  auto-complete, pluralize, or "correct" a name.
- Record each profiling rule VERBATIM in profiling_rules[].rule
- Fully qualified table names are DATABASE.SCHEMA.TABLE. If a name is not
  fully qualified, add a clarification question — do not guess the database
  or schema.
- If any required information is missing or ambiguous (system label, record
  key, match columns, discovery depth), add a question to clarifications[]
  instead of guessing.

Output format:
{"entity_config": { ...EntityConfig fields... }, "clarifications": []}
```

**User prompt:** the raw intake text, verbatim (one or more files concatenated).

**Output handling:** parse into `EntityConfig` + clarifications; retry once on parse failure. If `clarifications` is non-empty, print them as a numbered list and exit — do not proceed.

### 5.2 Schema Validation + Clarification Gate

1. Run introspection with **bound parameters** for every configured table:
   ```sql
   SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
   FROM {DATABASE}.INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA = %(schema)s AND TABLE_NAME = %(table)s
   ```
   plus row counts from `INFORMATION_SCHEMA.TABLES`.
2. Verify every table, record key, cross-system match column, and rule field exists. For each miss, generate a specific question and suggest the closest existing column name by string similarity — suggestion only, never auto-substitute.
3. Enforce the Definition of Ready (§2.3). Only a fully validated config proceeds. Save it to `configs/{entity}.json` (generated artifact, committed for audit).
4. For downstream prompts, `{user_request}` is composed deterministically as: the entity purpose plus the numbered profiling rules, verbatim.

### 5.3 Discovery — depth 1 (deterministic, metadata-only)

Purpose: "related tables which are linked to the main tables."

For each base table, search `INFORMATION_SCHEMA.COLUMNS` within the same database + schema for other tables containing a column whose name equals that base table's `record_key` (e.g., other Siebel tables carrying ROW_ID-referencing columns; other Salesforce tables carrying Id-referencing columns) or any configured match column. Where Snowflake referential constraints exist, read those too — but they are usually absent in landed/replicated data, so the name-match heuristic is primary.

Output per discovered table:

```python
class DiscoveredTable(BaseModel):
    fqn: str
    matched_column: str
    row_count: int | None
    link_basis: Literal["name_match", "constraint"]
```

The discovery list (a) is included in the planner prompt so `join_analysis` can target discovered tables, and (b) appears in the final report and dashboard as the "Related entities (depth 1)" panel. Depth is capped at 1 in v1. Discovery runs read-only metadata queries only — never SELECTs on data.

### 5.4 LLM Planner

Call the Anthropic API with `temperature=0`. Use these prompts verbatim:

**System prompt:**

```
You are a Data Profiling Planning Agent.

You convert business descriptions of data entities into structured profiling execution plans.

RULES:
- Do NOT generate SQL
- Do NOT execute anything
- Output ONLY valid JSON — no prose, no markdown fences
- Be deterministic and structured

You can only output these profiling task types:
1. null_analysis
2. distinct_count
3. uniqueness_check
4. pattern_analysis
5. distribution_analysis
6. join_analysis
7. cross_system_overlap
8. segment_variation

Each task must include:
- type
- table (fully qualified; omit for cross-system task types)
- columns (if applicable)
- join_table and join_key (only for join_analysis)
- match: left/right table and column (only for cross_system_overlap and segment_variation)
- segment_columns: table -> columns (only for segment_variation)
- business_reason (must quote or reference the profiling rule it serves)

Prioritize:
- critical fields (email, id, phone, country)
- relationship integrity (joins)
- data quality risk areas

Output format:
{"profiling_tasks": []}
```

**User prompt template:**

```
ENTITY: {entity}
PURPOSE: {purpose}

TABLES (with system and record key):
{tables}

CROSS-SYSTEM MATCHES:
{cross_system_matches}

PROFILING RULES (the user's own words — every rule must be covered):
{profiling_rules}

DISCOVERED RELATED TABLES (depth 1):
{discovered_tables}

SCHEMA METADATA:
{columns_with_types}

TASK:
Generate a profiling plan that covers every profiling rule. Set each task's
business_reason to the rule it serves.
```

**Output handling (critical):**
1. Strip any markdown fences, then `ProfilingPlan.model_validate_json()`.
2. Validate every task against the introspected schema: table must exist, every column must exist in that table, `join_table`/`join_key` must exist for join tasks. **Drop invalid tasks and log a warning** — never pass an unvalidated identifier downstream.
3. If JSON parsing fails: retry once with the parse error appended to the prompt. If it fails again, abort with a clear error.

### 5.5 SQL Generator (deterministic — this is NOT AI)

One fixed template per task type. Identifiers are only ever substituted **after** they have been validated against the introspected schema (whitelist approach — this is the SQL-injection defense, since identifiers cannot be bound parameters). All table identifiers are fully qualified (DATABASE.SCHEMA.TABLE) from the validated config.

```sql
-- null_analysis (per column)
SELECT
  '{column}' AS column_name,
  COUNT(*) AS total_rows,
  COUNT({column}) AS non_nulls,
  (COUNT(*) - COUNT({column})) / NULLIF(COUNT(*), 0) AS null_rate
FROM {table};

-- distinct_count (per column)
SELECT '{column}' AS column_name, COUNT(DISTINCT {column}) AS distinct_count
FROM {table};

-- uniqueness_check (per column)
SELECT
  '{column}' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT {column}) AS distinct_count,
  COUNT(DISTINCT {column}) / NULLIF(COUNT(*), 0) AS uniqueness_ratio
FROM {table};

-- pattern_analysis (per column; cap output)
SELECT
  REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE({column}, '[A-Z]', 'A'), '[a-z]', 'a'), '[0-9]', '9') AS pattern,
  COUNT(*) AS frequency
FROM {table}
WHERE {column} IS NOT NULL
GROUP BY pattern
ORDER BY frequency DESC
LIMIT 25;

-- distribution_analysis (per column; cap output)
SELECT {column} AS value, COUNT(*) AS frequency
FROM {table}
GROUP BY {column}
ORDER BY frequency DESC
LIMIT 50;

-- join_analysis (parent → child coverage, robust to one-to-many)
SELECT
  COUNT(*) AS total_records,
  COUNT(CASE WHEN EXISTS (
    SELECT 1 FROM {related_table} b WHERE b.{join_key} = a.{join_key}
  ) THEN 1 END) AS matched_records,
  COUNT(CASE WHEN EXISTS (
    SELECT 1 FROM {related_table} b WHERE b.{join_key} = a.{join_key}
  ) THEN 1 END) / NULLIF(COUNT(*), 0) AS match_rate
FROM {base_table} a;

-- cross_system_overlap (which records exist in both systems)
WITH l AS (SELECT DISTINCT {left_column} AS k FROM {left_table} WHERE {left_column} IS NOT NULL),
     r AS (SELECT DISTINCT {right_column} AS k FROM {right_table} WHERE {right_column} IS NOT NULL)
SELECT
  (SELECT COUNT(*) FROM l) AS left_keys,
  (SELECT COUNT(*) FROM r) AS right_keys,
  (SELECT COUNT(*) FROM l INNER JOIN r ON l.k = r.k) AS in_both,
  (SELECT COUNT(*) FROM l LEFT JOIN r ON l.k = r.k WHERE r.k IS NULL) AS left_only,
  (SELECT COUNT(*) FROM r LEFT JOIN l ON r.k = l.k WHERE l.k IS NULL) AS right_only;

-- segment_variation, part 1: distribution of each configured segment column
-- (reuses the distribution_analysis template once per segment column per system)

-- segment_variation, part 2: cross-system segment alignment for matched records
SELECT
  a.{left_segment_column} AS left_segment,
  b.{right_segment_column} AS right_segment,
  COUNT(*) AS frequency
FROM {left_table} a
JOIN {right_table} b
  ON a.{left_match_column} = b.{right_match_column}
GROUP BY 1, 2
ORDER BY frequency DESC
LIMIT 100;
```

Notes:
- `NULLIF` guards against division by zero on empty tables.
- Pattern analysis uses a 3-letter alphabet (`A`/`a`/`9`) so `john.doe@x.com` and `JOHN@X.COM` produce distinguishable shapes; punctuation is preserved.
- `LIMIT` on pattern/distribution queries keeps result payloads small enough for the insight LLM.
- For tables with `row_count > 10,000,000`, wrap the source table in `SAMPLE (1000000 ROWS)` and tag the result `sampled: true` in `detail`.

### 5.6 Snowflake Executor

- Single connection per run, credentials from environment variables (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD` or key-pair, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`). Never hardcode credentials.
- Execute tasks sequentially in v1 (simple, debuggable). Set a per-query timeout (default 120s).
- A failed query must **not** abort the run: log it, attach `{"status": "failed", "error": ...}` to that task, continue.
- Persist results:
  - `profiling_results_raw` — one row per executed query: run_id, task JSON, SQL text, raw result JSON, timestamp, status.
  - `profiling_results_aggregated` — one row per `MetricResult`.
  - In v1, write both as local JSONL files under `./runs/{run_id}/`; writing back to Snowflake tables is a v2 feature behind a flag.

### 5.7 Result Normalizer

Pure function: `(ProfilingTask, raw_rows) -> list[MetricResult]`. Examples:
- null_analysis → one `MetricResult` per column with `metric="null_rate"`.
- pattern_analysis → one `MetricResult` with `metric="top_patterns"`, `detail={"patterns": [{"pattern": "aaaa@aaa.aaa", "frequency": 9120}, ...]}`.
- join_analysis → `metric="match_rate"`.

### 5.8 LLM Insight Generator

`temperature=0`. Prompts verbatim:

**System prompt:**

```
You are a Data Quality Analyst.

You analyze profiling results and produce insights.

Rules:
- Be concise
- Focus on risk and business impact
- Identify anomalies and inconsistencies
- Suggest normalization opportunities
- Do not generate SQL
- Only reference metrics present in the input; never invent numbers

Output JSON in this format:
{
  "summary": "one-paragraph overall assessment",
  "findings": [
    {"severity": "high|medium|low", "column": "...", "finding": "...", "recommendation": "..."}
  ]
}
```

**User prompt (initial pass):**

```
ENTITY: {entity}
USER REQUEST: {user_request}

PROFILING RESULTS:
{results_json}
```

**User prompt (revision pass — appended on each review iteration):**

```
ENTITY: {entity}
USER REQUEST: {user_request}

PROFILING RESULTS:
{results_json}

YOUR PREVIOUS REPORT:
{previous_report_json}

REVIEWER FEEDBACK (you MUST address every item):
{feedback_json}

TASK:
Produce a revised report. Fix every feedback item. Do not introduce claims
that are not supported by the profiling results.
```

Validate the output against the `InsightReport` Pydantic model; retry once on parse failure.

### 5.9 LLM Review Agent (iterative quality gate)

**Purpose:** review the insight report against the user's request, the executed plan, and the normalized results. The report is only final when the reviewer returns no feedback. The review is grounded in the product definition: the system must (1) understand intent, (2) plan, (3) generate SQL, (4) execute, (5) return structured insights — the reviewer verifies that step 5 faithfully reflects steps 1–4.

`temperature=0`. Prompts verbatim:

**System prompt:**

```
You are a Data Quality Review Agent.

You review insight reports produced from data profiling results.
You do NOT generate SQL, do NOT request new analysis, and do NOT rewrite
the report yourself. You only critique it.

Review the report against these dimensions, in this order:

1. intent_alignment — does the report directly answer the user's business
   request (the entities, fields, and concerns they named)?
2. plan_coverage — does the report address every significant metric in the
   profiling results? Flag important results that were ignored.
3. grounding — is every number and claim in the report traceable to the
   profiling results provided? Flag any invented or altered figure.
4. severity_calibration — are high/medium/low severities justified by the
   actual metric values?
5. actionability — is every recommendation concrete (e.g. "standardize
   phone to E.164") rather than vague (e.g. "improve data quality")?

RULES:
- Output ONLY valid JSON — no prose, no markdown fences
- If the report passes all dimensions, output {"approved": true, "feedback": []}
- If not, approved must be false and every feedback item must include:
  - dimension (one of the five above)
  - issue (what is wrong, citing the specific finding or metric)
  - required_change (the precise correction the analyst must make)
- Do not raise stylistic or subjective preferences; only raise issues that
  change correctness, coverage, or usefulness
- Never approve a report that cites a number absent from the profiling results

Output format:
{"approved": false, "feedback": [{"dimension": "...", "issue": "...", "required_change": "..."}]}
```

**User prompt:**

```
ENTITY: {entity}
USER REQUEST: {user_request}

EXECUTED PROFILING PLAN (task types and targets only):
{plan_summary_json}

PROFILING RESULTS:
{results_json}

INSIGHT REPORT UNDER REVIEW:
{report_json}
```

**Loop logic (deterministic orchestration in `reviewer.py` / `pipeline.py`):**

```
report = generate_insights(results)
for i in range(1, max_review_iterations + 1):      # default 3, configurable
    feedback = review(report, results, plan, request)
    save ./runs/{run_id}/review_{i}.json
    if feedback.approved:
        return ReviewedReport(report, "approved", i, history)
    report = generate_insights(results, previous=report, feedback=feedback)
return ReviewedReport(report, "max_iterations_reached", max_review_iterations, history)
```

Hard rules:
- `approved=true` with non-empty feedback is a contract violation → treat as parse failure and retry once.
- The loop is bounded by `max_review_iterations` (default 3) to prevent infinite reviewer/generator ping-pong; if the cap is hit, ship the latest report but mark `review_status: max_iterations_reached` prominently at the top of `report.md`.
- The reviewer receives only the plan summary, results, and report — never SQL, never DB credentials, and it cannot add tasks. If it believes analysis is missing, that surfaces as `plan_coverage` feedback for the human, not as a new query.
- Every iteration (report version + feedback) is persisted to `./runs/{run_id}/` for auditability.

### 5.10 Visualization Renderer (deterministic — NOT AI)

Renders `./runs/{run_id}/dashboard.html` — a single self-contained HTML file (plotly) built ONLY from `MetricResult` records, the discovery list, and the approved insight report. No LLM involvement; rendering is pure templated code.

Required panels (render only those with data for the run):

1. **Run header** — entity, purpose, profiling rules, review status + iteration count
2. **Missing-data chart** — null_rate per column, grouped by table, sorted worst-first, severity color bands
3. **Uniqueness / distinct summary** table per table
4. **Pattern analysis** — top patterns per column with frequencies
5. **Segment variation** — top-N value charts per segment column per system, plus a heatmap of the cross-system segment cross-tab (e.g., Salesforce record type vs Siebel market_class_cd for matched customers)
6. **Cross-system overlap** — bar set: left-only / in-both / right-only, with match rate
7. **Related entities (depth 1)** — discovered tables with link basis and row counts, plus join coverage where join_analysis ran
8. **Insight report** — summary + severity-tagged findings from the approved report

Charts must label tables by system (e.g., "Siebel: s_org_ext", "Salesforce: accounts") so cross-system comparisons read naturally. The panel set is the visualization template — fixed structure, data-driven content.

---

## 6. Project structure

```
profiler/
  __main__.py          # CLI: extract, run, plan-only, introspect
  config.py            # env + settings (Snowflake creds, max_review_iterations)
  models.py            # all Pydantic models (§4.1–4.6), incl. EntityConfig, DiscoveredTable
  extractor.py         # LLM intake extraction (§5.1)
  validation.py        # schema validation + clarification gate (§5.2)
  introspection.py
  discovery.py         # depth-1 related-table discovery (§5.3)
  planner.py           # LLM call + validation + retry
  sql_generator.py     # pure functions, templates (8 task types)
  executor.py
  normalizer.py        # pure functions
  insights.py          # LLM call + validation, supports revision passes
  reviewer.py          # LLM review call + iterative review loop orchestration
  visualizer.py        # deterministic dashboard.html renderer (§5.10)
  llm_client.py        # thin Anthropic wrapper (temperature=0, retries)
intake/
  customer.txt         # v1 feasibility input — the plain-text example from §1/§2
configs/
  customer.json        # extracted + validated EntityConfig (generated, committed for audit)
tests/
  test_models.py
  test_extractor_validation.py  # mocked LLM: names copied verbatim, gaps -> clarifications
  test_sql_generator.py    # golden-file tests: task in -> exact SQL out (all 8 types)
  test_normalizer.py
  test_planner_validation.py   # invalid tables/columns are dropped
  test_discovery.py        # fixture INFORMATION_SCHEMA -> expected related tables
  test_review_loop.py      # mocked LLMs: approval exits loop, cap enforced,
                           # approved=true with feedback rejected
  test_visualizer.py       # fixture MetricResults -> dashboard.html renders expected panels
  fixtures/
```

---

## 7. CLI behavior

```
python -m profiler extract --input intake/customer.txt   # extraction + validation only; prints clarifying questions, or saves configs/customer.json when ready
python -m profiler run --input intake/customer.txt       # full pipeline end-to-end
python -m profiler run --input intake/customer.txt --plan-only   # validated plan + generated SQL, executes nothing
python -m profiler introspect --config configs/customer.json     # prints schema metadata + depth-1 discovery results
```

`extract` and `--plan-only` are mandatory in v1 — they are the primary debugging and trust-building tools. The clarification flow is non-interactive: questions are printed, the user edits the intake text, and reruns.

---

## 8. MUST HAVE checklist

- [ ] Plain-text intake support — free text AND labeled template — with v1 input at `intake/customer.txt` (the §1 example)
- [ ] LLM context extractor: names copied verbatim, gaps become clarifications, JSON-only output, one retry
- [ ] Schema validation + clarification gate enforcing the Definition of Ready (§2.3); validated config saved to `configs/{entity}.json`
- [ ] Depth-1 discovery of related tables (deterministic, metadata-only)
- [ ] LLM planner with JSON-only output, schema-validated, with one retry; every profiling rule covered
- [ ] Identifier whitelist validation before any SQL substitution (fully qualified names)
- [ ] Deterministic SQL generator covering all 8 task types
- [ ] Sequential Snowflake executor with per-query error isolation
- [ ] Raw + aggregated result persistence per run
- [ ] Result normalizer producing `MetricResult` records
- [ ] LLM insight generator with structured JSON output and revision support
- [ ] LLM review agent with the five-dimension feedback template
- [ ] Iterative review loop: regenerate → re-review until approved, capped at `max_review_iterations` (default 3, configurable)
- [ ] Every report version and review feedback persisted per run
- [ ] Deterministic `dashboard.html` with the §5.10 panel set; final `report.md` shows review status and iteration count
- [ ] `extract` and `--plan-only` dry-run modes
- [ ] Unit tests: extractor validation, SQL golden files (8 types), normalizer, planner validation, discovery, review loop, visualizer — all with mocked LLMs / fixtures
- [ ] README with setup, env vars, and the Customer end-to-end example

## 9. MUST NOT

- ❌ No LLM-generated SQL, ever — including "fixing" failed queries with the LLM
- ❌ No free-text output from the extractor, planner, or reviewer — JSON only, schema-validated
- ❌ The extractor must never invent, auto-complete, or "correct" table/column names — anything unresolved becomes a clarification question
- ❌ No ad-hoc queries outside the 8 templates
- ❌ No identifier reaches a SQL string without passing schema whitelist validation
- ❌ No DML/DDL — the executor runs SELECT statements only (enforce with a startswith check as a belt-and-braces guard)
- ❌ Discovery runs metadata queries only — never SELECTs on data
- ❌ Visualization is deterministic — no LLM-generated charts, numbers, or chart text
- ❌ No credentials in code or config files
- ❌ The review agent must never trigger new queries, modify the plan, or rewrite the report itself — critique only
- ❌ No unbounded review loops — the iteration cap is mandatory
- ❌ No hardcoded entity, table, or column names in code — everything entity-specific comes from the extracted `EntityConfig`. This applies to harness stubs too: canned data lives in fixture files, never in Python constants
- ❌ No multi-entity orchestration, entity registries, or web UI in v1 — one intake text per run is the entire entity mechanism

## 10. Build order (harness first — implement and verify in this sequence)

0. **Harness skeleton (end-to-end with stubs).** Wire all 11 pipeline stages with stub implementations. The harness must NOT be hardcoded:
   - Every stub implements the **same interface** (same function signature, same Pydantic input/output models) as the real component it stands in for — swapping a stub for the real implementation must require zero changes to the pipeline orchestration or to any other stage.
   - All canned data lives in **fixture files** under `tests/fixtures/` (intake text, extractor output JSON, schema metadata JSON, query result rows, planner/insight/review JSON) — never as constants inside stub code. The stubs only load and return fixture files.
   - The orchestration code written in Phase 0 is the **final** orchestration code — it is entity-agnostic, driven entirely by `EntityConfig` and the stage interfaces, and is not rewritten in later phases.
   - Acid test: replacing the Customer fixture files with a different entity's fixtures must make the harness run end-to-end for that entity with zero code changes.
   `python -m profiler run --input intake/customer.txt --harness` must already produce a `report.md` and `dashboard.html` from fixture data. This proves the templated structure before any real logic exists, and every later phase replaces exactly one stub.
1. **Data models** (`models.py`) + `intake/customer.txt` + tests.
2. **SQL generator** (all 8 task types) + golden-file tests — pure functions, easiest to verify.
3. **Normalizer** + tests with fixture rows.
4. **Extractor + validation gate** — mocked-LLM tests first (verbatim names, clarifications); then live extraction of `intake/customer.txt` against the real Snowflake schema, producing `configs/customer.json`.
5. **Discovery** — fixture INFORMATION_SCHEMA tests, then live against the Siebel/Salesforce schemas.
6. **Planner** — mock the LLM in tests; verify validation drops bad tasks and every rule is covered.
7. **Executor** — wire end-to-end with `--plan-only` first, then live execution.
8. **Insight generator + review loop** — mocked LLMs first (approval path, revision path, iteration cap), then live.
9. **Visualizer** — fixture-driven tests for all panels, then live dashboard from a real run.
10. **README + live end-to-end** on the Siebel/Salesforce Customer feasibility case.

## 11. Acceptance criteria (definition of done)

**Principle: the acceptance criteria ARE the review rubric.** A report is accepted on exactly the same five dimensions the Review Agent scores (`ReviewDimension` in §4.6) — no separate quality bar. The Review Agent automates these checks per run; the engineer verifies the same rubric once during build sign-off using the feasibility case below.

### Part A — Report acceptance (the five review dimensions)

Given `intake/customer.txt` (the §1 plain-text input, verbatim), the final report is accepted only when it passes all five dimensions:

| # | Dimension | Acceptance check for the feasibility case |
|---|---|---|
| 1 | **intent_alignment** | The report directly addresses the user's two stated rules: segment variation (record type in Salesforce; market_class_cd and market_type_cd in Siebel) and customers present in both systems. Findings trace back to the verbatim rules. |
| 2 | **plan_coverage** | Every executed task is reflected: `segment_variation` across both systems, `cross_system_overlap` on ou_num = Customer_Number__c, `null_analysis` on key fields, and discovery/join findings for depth-1 related tables — each maps to at least one finding or an explicit "no issue found." |
| 3 | **grounding** | Every number and claim is traceable to a `MetricResult` from this run. Zero invented or altered figures. |
| 4 | **severity_calibration** | Ratings justified by values (e.g., 40% of Siebel customers absent from Salesforce may be `high`; 0.5% must not be). |
| 5 | **actionability** | Recommendations are concrete (e.g., "map Siebel market_class_cd values X, Y to Salesforce record type Z before migration") — never vague ("improve data quality"). |

A run is **done** when the Review Agent returns `{"approved": true, "feedback": []}` against this rubric, or the iteration cap is reached and `max_iterations_reached` is clearly surfaced in `report.md` and the dashboard header.

### Part B — System acceptance (build sign-off)

1. **Extraction:** given `intake/customer.txt`, the extractor produces an `EntityConfig` with every table/column name verbatim (spark_ods.siebel.s_org_ext, ou_num, Customer_Number__c, row_id, Id, ...) and zero invented names; given an intake with a missing record key, it produces a clarification question instead of a config.
2. **Validation gate:** a config referencing a non-existent column blocks the run with a specific question (and a closest-match suggestion).
3. **Discovery:** on a fixture schema, depth-1 discovery returns exactly the tables sharing the record-key columns; live, the discovered list appears in the planner prompt, report, and dashboard.
4. **Plan + SQL:** validated plan covers every profiling rule; generated SQL matches the templates exactly (golden tests, all 8 types).
5. **Execution:** a single failed query does not abort the run.
6. **Review loop:** runs until approval or `max_review_iterations`, persisting every report version and feedback round. Mocked-LLM tests prove one rejection per dimension, the approval path, and cap termination.
7. **Visualization:** `dashboard.html` renders the §5.10 panels from the run's `MetricResult` records, including the segment cross-tab heatmap and the overlap bars.
8. All unit tests pass; `extract` and `--plan-only` run with no Snowflake writes; the Phase-0 harness still passes end-to-end with stubs.

## 12. Positioning (context, not a build requirement)

This is not a one-off script. It is a reusable AI profiling agent framework for enterprise data onboarding and migration readiness. v1 proves feasibility on a single entity — Customer across Siebel and Salesforce — but because all entity knowledge arrives as plain text and lives in the extracted `EntityConfig`, extending to a new entity later means writing a new intake text file, not new code. Build for the Customer case; design nothing that would prevent the next intake from working unchanged.
