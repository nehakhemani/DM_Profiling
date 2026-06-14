from __future__ import annotations

import json
from pathlib import Path

from .models import DiscoveredTable, EntityConfig, MetricResult, ReviewedReport


def render_dashboard(
    reviewed_report: ReviewedReport,
    results: list[MetricResult],
    discovered_tables: list[DiscoveredTable],
    config: EntityConfig,
    run_id: str,
    output_dir: str,
) -> None:
    """
    Writes report.md and dashboard.html to output_dir.

    Phase 0 stub: produces minimal but valid files containing all key data
    (entity, review status, findings, metrics, discovered tables).
    Full plotly panels are implemented in Phase 9.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    _write_report_md(reviewed_report, config, out)
    _write_dashboard_html(reviewed_report, results, discovered_tables, config, run_id, out)


def _write_report_md(reviewed_report: ReviewedReport, config: EntityConfig, out: Path) -> None:
    report = reviewed_report.report
    status = reviewed_report.review_status
    iterations = reviewed_report.iterations

    if status == "max_iterations_reached":
        header = f"> **WARNING:** Review did not converge — max iterations ({iterations}) reached."
    else:
        header = f"> Review status: **{status}** after {iterations} iteration(s)."

    rules = "\n".join(f"{i+1}. {r.rule}" for i, r in enumerate(config.profiling_rules))
    findings_md = "\n\n".join(
        f"**[{f.severity.upper()}]** {('`' + f.column + '`  ') if f.column else ''}"
        f"{f.finding}\n\n*Recommendation:* {f.recommendation}"
        for f in report.findings
    )

    md = f"""# Profiling Report: {config.entity}

{header}

**Purpose:** {config.purpose}

## Profiling Rules
{rules}

## Summary
{report.summary}

## Findings
{findings_md}
"""
    (out / "report.md").write_text(md, encoding="utf-8")


def _write_dashboard_html(
    reviewed_report: ReviewedReport,
    results: list[MetricResult],
    discovered_tables: list[DiscoveredTable],
    config: EntityConfig,
    run_id: str,
    out: Path,
) -> None:
    report = reviewed_report.report

    def _esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Build findings rows
    finding_rows = "".join(
        f"<tr><td>{_esc(f.severity)}</td><td>{_esc(f.column or '')}</td>"
        f"<td>{_esc(f.finding)}</td><td>{_esc(f.recommendation)}</td></tr>"
        for f in report.findings
    )

    # Build metric rows
    metric_rows = "".join(
        f"<tr><td>{_esc(r.table)}</td><td>{_esc(r.column or '')}</td>"
        f"<td>{_esc(r.metric)}</td><td>{_esc(str(r.value))}</td></tr>"
        for r in results
    )

    # Build discovery rows
    disc_rows = "".join(
        f"<tr><td>{_esc(t.fqn)}</td><td>{_esc(t.matched_column)}</td>"
        f"<td>{_esc(str(t.row_count))}</td><td>{_esc(t.link_basis)}</td></tr>"
        for t in discovered_tables
    )

    status_badge = (
        '<span style="color:green">&#10003; approved</span>'
        if reviewed_report.review_status == "approved"
        else '<span style="color:orange">&#9888; max_iterations_reached</span>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Profiling Dashboard — {_esc(config.entity)}</title>
<style>
  body {{ font-family: sans-serif; margin: 2rem; color: #222; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: .4rem; }}
  h2 {{ margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .5rem; }}
  th, td {{ border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; font-size: .9rem; }}
  th {{ background: #f0f0f0; }}
  .meta {{ color: #555; font-size: .9rem; margin: .3rem 0; }}
</style>
</head>
<body>
<h1>Profiling Dashboard — {_esc(config.entity)}</h1>
<p class="meta"><strong>Run ID:</strong> {_esc(run_id)}</p>
<p class="meta"><strong>Review status:</strong> {status_badge}
  &nbsp; ({reviewed_report.iterations} iteration(s))</p>
<p class="meta"><strong>Purpose:</strong> {_esc(config.purpose)}</p>

<h2>Profiling Rules</h2>
<ol>{"".join(f"<li>{_esc(r.rule)}</li>" for r in config.profiling_rules)}</ol>

<h2>Summary</h2>
<p>{_esc(report.summary)}</p>

<h2>Findings</h2>
<table>
<thead><tr><th>Severity</th><th>Column</th><th>Finding</th><th>Recommendation</th></tr></thead>
<tbody>{finding_rows}</tbody>
</table>

<h2>Metric Results</h2>
<table>
<thead><tr><th>Table</th><th>Column</th><th>Metric</th><th>Value</th></tr></thead>
<tbody>{metric_rows}</tbody>
</table>

<h2>Related Entities (depth 1)</h2>
<table>
<thead><tr><th>Table</th><th>Matched Column</th><th>Row Count</th><th>Link Basis</th></tr></thead>
<tbody>{disc_rows}</tbody>
</table>
</body>
</html>
"""
    (out / "dashboard.html").write_text(html, encoding="utf-8")
