from __future__ import annotations

import json

from .config import Settings
from .models import DiscoveredTable, EntityConfig



def run_discovery(config: EntityConfig, settings: Settings) -> list[DiscoveredTable]:
    """
    Depth-1 discovery: finds tables in the same schema as each base table that
    reference its record key, using INFORMATION_SCHEMA metadata only (no data SELECTs).

    Two passes per base table:
      1. FK constraints  (link_basis="constraint") — precise but often absent in ODS layers
      2. Column name match (link_basis="name_match") — finds tables sharing the key column name

    Harness: loads tests/fixtures/discovered_tables.json.
    Real: queries Snowflake INFORMATION_SCHEMA via externalbrowser SSO.
    """
    if settings.harness:
        raw = json.loads(settings.fixture_path("discovered_tables.json").read_text(encoding="utf-8-sig"))
        return [DiscoveredTable.model_validate(t) for t in raw]

    return _live_discovery(config, settings)


# ── Live discovery ────────────────────────────────────────────────────────────

def _live_discovery(config: EntityConfig, settings: Settings) -> list[DiscoveredTable]:
    from ._snowflake import connect, safe_execute as _safe_exec

    print("\n  [discovery] Opening Snowflake connection (externalbrowser SSO)...")
    conn = connect()
    cur  = conn.cursor()

    seen:    dict[str, DiscoveredTable] = {}   # fqn → best result
    base_fqns = {t.fqn.upper() for t in config.tables}

    for src in config.tables:
        catalog, schema, table = _parse_fqn(src.fqn)
        key = src.record_key

        print(f"  [discovery] {src.fqn} (key={key}) ...")

        # Pass 1 — FK constraints
        for dt in _fk_discovery(cur, catalog, schema, table, key, base_fqns):
            if dt.fqn.upper() not in seen:
                seen[dt.fqn.upper()] = dt

        # Pass 2 — column name match (fills gaps where no FK constraints exist)
        for dt in _name_match_discovery(cur, catalog, schema, table, key, base_fqns):
            fqn_upper = dt.fqn.upper()
            if fqn_upper not in seen:
                seen[fqn_upper] = dt

    conn.close()

    results = sorted(seen.values(), key=lambda d: (d.row_count or 0), reverse=True)
    print(f"  [discovery] Found {len(results)} related table(s)")
    return results


def _fk_discovery(
    cur, catalog: str, schema: str, table: str,
    record_key: str, exclude: set[str],
) -> list[DiscoveredTable]:
    sql = f"""
SELECT DISTINCT
    fk_tc.TABLE_CATALOG || '.' || fk_tc.TABLE_SCHEMA || '.' || fk_tc.TABLE_NAME  AS fqn,
    fk_kcu.COLUMN_NAME                                                             AS matched_column,
    t.ROW_COUNT                                                                    AS row_count
FROM {catalog}.INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
JOIN {catalog}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS  pk_tc
     ON pk_tc.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
     AND pk_tc.TABLE_CATALOG  = rc.CONSTRAINT_CATALOG
JOIN {catalog}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS  fk_tc
     ON fk_tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
     AND fk_tc.TABLE_CATALOG  = rc.CONSTRAINT_CATALOG
JOIN {catalog}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE   fk_kcu
     ON fk_kcu.CONSTRAINT_NAME  = fk_tc.CONSTRAINT_NAME
     AND fk_kcu.TABLE_CATALOG   = fk_tc.TABLE_CATALOG
JOIN {catalog}.INFORMATION_SCHEMA.TABLES t
     ON t.TABLE_NAME    = fk_tc.TABLE_NAME
     AND t.TABLE_SCHEMA = fk_tc.TABLE_SCHEMA
     AND t.TABLE_CATALOG = fk_tc.TABLE_CATALOG
WHERE pk_tc.TABLE_CATALOG = '{catalog}'
  AND pk_tc.TABLE_SCHEMA  = '{schema}'
  AND pk_tc.TABLE_NAME    = '{table}'
ORDER BY row_count DESC NULLS LAST
LIMIT 30
"""
    try:
        _safe_exec(cur, sql)
        rows = cur.fetchall()
    except Exception:
        return []   # INFORMATION_SCHEMA may not expose referential constraints in all editions

    results = []
    for fqn, col, rc in rows:
        if fqn.upper() not in exclude:
            results.append(DiscoveredTable(
                fqn=fqn, matched_column=col,
                row_count=int(rc) if rc is not None else None,
                link_basis="constraint",
            ))
    return results


def _name_match_discovery(
    cur, catalog: str, schema: str, table: str,
    record_key: str, exclude: set[str],
    limit: int = 20,
) -> list[DiscoveredTable]:
    sql = f"""
SELECT DISTINCT
    c.TABLE_CATALOG || '.' || c.TABLE_SCHEMA || '.' || c.TABLE_NAME  AS fqn,
    c.COLUMN_NAME                                                      AS matched_column,
    t.ROW_COUNT                                                        AS row_count
FROM {catalog}.INFORMATION_SCHEMA.COLUMNS c
JOIN {catalog}.INFORMATION_SCHEMA.TABLES  t
     ON  t.TABLE_CATALOG = c.TABLE_CATALOG
     AND t.TABLE_SCHEMA  = c.TABLE_SCHEMA
     AND t.TABLE_NAME    = c.TABLE_NAME
WHERE c.TABLE_CATALOG   = '{catalog}'
  AND c.TABLE_SCHEMA    = '{schema}'
  AND UPPER(c.COLUMN_NAME) = UPPER('{record_key}')
  AND UPPER(c.TABLE_NAME)  != UPPER('{table}')
  AND t.TABLE_TYPE = 'BASE TABLE'
ORDER BY t.ROW_COUNT DESC NULLS LAST
LIMIT {limit}
"""
    _safe_exec(cur, sql)
    rows = cur.fetchall()

    results = []
    for fqn, col, rc in rows:
        if fqn.upper() not in exclude:
            results.append(DiscoveredTable(
                fqn=fqn, matched_column=col,
                row_count=int(rc) if rc is not None else None,
                link_basis="name_match",
            ))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_fqn(fqn: str) -> tuple[str, str, str]:
    parts = fqn.upper().split(".")
    if len(parts) != 3:
        raise ValueError(f"FQN must be catalog.schema.table, got: {fqn}")
    return parts[0], parts[1], parts[2]
