from __future__ import annotations

import csv
import re
from pathlib import Path

from ._snowflake import connect as _sf_connect, safe_execute


def run_sql_file(sql_path: str, results_dir: str) -> list[str]:
    """
    Parses sql_path into labelled blocks, executes each against Snowflake
    (SPARKNZ-DATA profile from ~/.snowflake/connections.toml), and writes
    one CSV per block under results_dir.

    Only SELECT/WITH statements are permitted — safe_execute blocks anything else.
    Session timeout is set to 60s by the connection helper.

    Returns a list of written CSV paths.
    """
    blocks = _parse_blocks(Path(sql_path).read_text(encoding="utf-8-sig"))
    if not blocks:
        raise ValueError(f"No query blocks found in {sql_path}")

    print("\nConnecting to Snowflake (externalbrowser SSO)...")
    print("A browser tab will open — log in to continue.\n")
    conn = _sf_connect()

    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for block in blocks:
        safe_label = block["label"].encode("ascii", "replace").decode()
        print(f"  Running task {block['num']:>2}: {safe_label} ...", end=" ", flush=True)
        try:
            cur = conn.cursor()
            safe_execute(cur, block["sql"])
            rows = cur.fetchall()
            col_names = [d[0] for d in cur.description]

            csv_path = out / block["csv_name"]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(col_names)
                writer.writerows(rows)

            print(f"{len(rows)} rows -> {csv_path.name.encode('ascii', 'replace').decode()}")
            written.append(str(csv_path))
        except Exception as exc:
            print(f"FAILED: {exc}")

    conn.close()
    return written


# ── SQL file parser ───────────────────────────────────────────────────────────

_BOX     = "─"   # U+2500 BOX DRAWINGS LIGHT HORIZONTAL
_TASK_RE = re.compile(rf"-- {_BOX}+ Task (\d+): (.+?) {_BOX}+")
_CSV_RE  = re.compile(r"-- Export this result as: (.+\.csv)")


def _parse_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    current: dict | None = None
    sql_lines: list[str] = []

    for line in text.splitlines():
        m_task = _TASK_RE.match(line)
        if m_task:
            if current is not None:
                current["sql"] = _extract_sql(sql_lines)
                if current["sql"]:
                    blocks.append(current)
            current = {"num": int(m_task.group(1)), "label": m_task.group(2).strip(),
                       "csv_name": "", "sql": ""}
            sql_lines = []
            continue

        if current is None:
            continue

        m_csv = _CSV_RE.match(line)
        if m_csv:
            current["csv_name"] = m_csv.group(1).strip()
            continue

        if not line.startswith("--"):
            sql_lines.append(line)

    if current is not None:
        current["sql"] = _extract_sql(sql_lines)
        if current["sql"]:
            blocks.append(current)

    for b in blocks:
        if not b["csv_name"]:
            b["csv_name"] = f"task_{b['num']:02d}.csv"

    return blocks


def _extract_sql(lines: list[str]) -> str:
    return "\n".join(lines).strip().rstrip(";").strip()
