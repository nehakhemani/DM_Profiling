from __future__ import annotations

from .models import CrossSystemMatch, ProfilingTask


# ── Public entry point ────────────────────────────────────────────────────────

def generate_sql(
    task: ProfilingTask,
    column: str | None,
    validated_identifiers: set[str],
) -> str:
    """
    Returns a single SELECT SQL string for the given (task, column) pair.
    column is None for whole-task types (join_analysis, cross_system_overlap,
    segment_variation cross-tab).

    Raises ValueError if any identifier is not in validated_identifiers.
    """
    t = task.type

    if t == "null_analysis":
        return _null_analysis(_ok(task.table, validated_identifiers),
                              _ok_col(task.table, column, validated_identifiers))

    if t == "distinct_count":
        return _distinct_count(_ok(task.table, validated_identifiers),
                               _ok_col(task.table, column, validated_identifiers))

    if t == "uniqueness_check":
        return _uniqueness_check(_ok(task.table, validated_identifiers),
                                 _ok_col(task.table, column, validated_identifiers))

    if t == "pattern_analysis":
        return _pattern_analysis(_ok(task.table, validated_identifiers),
                                 _ok_col(task.table, column, validated_identifiers))

    if t == "distribution_analysis":
        return _distribution_analysis(_ok(task.table, validated_identifiers),
                                      _ok_col(task.table, column, validated_identifiers))

    if t == "join_analysis":
        return _join_analysis(
            _ok(task.table, validated_identifiers),
            _ok(task.join_table, validated_identifiers),
            task.join_key,   # join_key is validated by planner against base table schema
        )

    if t == "cross_system_overlap":
        m = task.match
        return _cross_system_overlap(
            _ok(m.left_table, validated_identifiers), m.left_column,
            _ok(m.right_table, validated_identifiers), m.right_column,
        )

    if t == "segment_variation":
        # column carries the context: "left_segment|right_segment" or None for cross-tab
        if column is None:
            m = task.match
            return _segment_crosstab(
                _ok(m.left_table, validated_identifiers), m.left_column,
                _ok(m.right_table, validated_identifiers), m.right_column,
                column,   # resolved by caller
            )
        # individual segment distribution reuses distribution_analysis
        tbl, col = column.split(".", 1)
        return _distribution_analysis(_ok(tbl, validated_identifiers),
                                      _ok_col(tbl, col, validated_identifiers))

    raise ValueError(f"Unknown task type: {t}")


# ── Whitelist helpers ─────────────────────────────────────────────────────────

def _ok(identifier: str, whitelist: set[str]) -> str:
    if identifier not in whitelist:
        raise ValueError(
            f"Identifier '{identifier}' not in validated whitelist — refusing SQL substitution"
        )
    return identifier


def _ok_col(table: str, column: str, whitelist: set[str]) -> str:
    key = f"{table}.{column}"
    if key not in whitelist:
        raise ValueError(
            f"Column '{key}' not in validated whitelist — refusing SQL substitution"
        )
    return column


# ── SQL templates (§5.5) ──────────────────────────────────────────────────────

def _null_analysis(table: str, column: str) -> str:
    return (
        f"SELECT\n"
        f"  '{column}' AS column_name,\n"
        f"  COUNT(*) AS total_rows,\n"
        f"  COUNT({column}) AS non_nulls,\n"
        f"  (COUNT(*) - COUNT({column})) / NULLIF(COUNT(*), 0) AS null_rate\n"
        f"FROM {table}"
    )


def _distinct_count(table: str, column: str) -> str:
    return (
        f"SELECT '{column}' AS column_name, COUNT(DISTINCT {column}) AS distinct_count\n"
        f"FROM {table}"
    )


def _uniqueness_check(table: str, column: str) -> str:
    return (
        f"SELECT\n"
        f"  '{column}' AS column_name,\n"
        f"  COUNT(*) AS total_rows,\n"
        f"  COUNT(DISTINCT {column}) AS distinct_count,\n"
        f"  COUNT(DISTINCT {column}) / NULLIF(COUNT(*), 0) AS uniqueness_ratio\n"
        f"FROM {table}"
    )


def _pattern_analysis(table: str, column: str) -> str:
    return (
        f"SELECT\n"
        f"  REGEXP_REPLACE(\n"
        f"    REGEXP_REPLACE(\n"
        f"      REGEXP_REPLACE({column}, '[A-Z]', 'A'),\n"
        f"    '[a-z]', 'a'),\n"
        f"  '[0-9]', '9') AS pattern,\n"
        f"  COUNT(*) AS frequency\n"
        f"FROM {table}\n"
        f"WHERE {column} IS NOT NULL\n"
        f"GROUP BY pattern\n"
        f"ORDER BY frequency DESC\n"
        f"LIMIT 25"
    )


def _distribution_analysis(table: str, column: str) -> str:
    return (
        f"SELECT {column} AS value, COUNT(*) AS frequency\n"
        f"FROM {table}\n"
        f"GROUP BY {column}\n"
        f"ORDER BY frequency DESC\n"
        f"LIMIT 50"
    )


def _join_analysis(base_table: str, related_table: str, join_key: str) -> str:
    return (
        f"SELECT\n"
        f"  COUNT(*) AS total_records,\n"
        f"  COUNT(CASE WHEN EXISTS (\n"
        f"    SELECT 1 FROM {related_table} b WHERE b.{join_key} = a.{join_key}\n"
        f"  ) THEN 1 END) AS matched_records,\n"
        f"  COUNT(CASE WHEN EXISTS (\n"
        f"    SELECT 1 FROM {related_table} b WHERE b.{join_key} = a.{join_key}\n"
        f"  ) THEN 1 END) / NULLIF(COUNT(*), 0) AS match_rate\n"
        f"FROM {base_table} a"
    )


def _cross_system_overlap(
    left_table: str, left_col: str,
    right_table: str, right_col: str,
) -> str:
    return (
        f"WITH l AS (\n"
        f"  SELECT DISTINCT {left_col} AS k\n"
        f"  FROM {left_table}\n"
        f"  WHERE {left_col} IS NOT NULL\n"
        f"),\n"
        f"r AS (\n"
        f"  SELECT DISTINCT {right_col} AS k\n"
        f"  FROM {right_table}\n"
        f"  WHERE {right_col} IS NOT NULL\n"
        f")\n"
        f"SELECT\n"
        f"  (SELECT COUNT(*) FROM l)                                  AS left_keys,\n"
        f"  (SELECT COUNT(*) FROM r)                                  AS right_keys,\n"
        f"  (SELECT COUNT(*) FROM l INNER JOIN r ON l.k = r.k)       AS in_both,\n"
        f"  (SELECT COUNT(*) FROM l LEFT  JOIN r ON l.k = r.k WHERE r.k IS NULL) AS left_only,\n"
        f"  (SELECT COUNT(*) FROM r LEFT  JOIN l ON r.k = l.k WHERE l.k IS NULL) AS right_only"
    )


def _segment_crosstab(
    left_table: str, left_match_col: str,
    right_table: str, right_match_col: str,
    _unused: None,
    left_seg: str = "left_segment",
    right_seg: str = "right_segment",
) -> str:
    # Caller must supply the actual segment column names via left_seg / right_seg.
    # The default names are placeholders — the sql_writer substitutes real values.
    return (
        f"SELECT\n"
        f"  a.{left_seg}  AS left_segment,\n"
        f"  b.{right_seg} AS right_segment,\n"
        f"  COUNT(*) AS frequency\n"
        f"FROM {left_table} a\n"
        f"JOIN {right_table} b\n"
        f"  ON a.{left_match_col} = b.{right_match_col}\n"
        f"GROUP BY 1, 2\n"
        f"ORDER BY frequency DESC\n"
        f"LIMIT 100"
    )


def segment_crosstab_sql(
    left_table: str, left_match_col: str, left_seg_col: str,
    right_table: str, right_match_col: str, right_seg_col: str,
) -> str:
    """Direct call for the cross-tab part of segment_variation (used by sql_writer)."""
    return (
        f"SELECT\n"
        f"  a.{left_seg_col}  AS left_segment,\n"
        f"  b.{right_seg_col} AS right_segment,\n"
        f"  COUNT(*) AS frequency\n"
        f"FROM {left_table} a\n"
        f"JOIN {right_table} b\n"
        f"  ON a.{left_match_col} = b.{right_match_col}\n"
        f"GROUP BY 1, 2\n"
        f"ORDER BY frequency DESC\n"
        f"LIMIT 100"
    )
