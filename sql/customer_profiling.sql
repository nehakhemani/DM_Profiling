-- ======================================================================
-- Profiling run  : Customer
-- Run ID         : 629554ec
-- Generated      : 2026-06-14 13:53
-- Purpose        : Data discovery and profiling for the customer entity (CRM consolidation)
-- ----------------------------------------------------------------------
-- Profiling rules:
--   1. Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
--   2. Customers which are present in both systems
--   3. Missing important data on key fields
-- ======================================================================
-- HOW TO USE:
--   1. Open this file in VS Code with the Snowflake extension.
--   2. Run each block (Ctrl+Enter or Run All).
--   3. Export each result set as CSV / Excel.
-- ======================================================================

-- ── Task 1: null_analysis | s_org_ext.row_id ──────────────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_01_null_analysis__s_org_ext_row_id.csv
SELECT
  'row_id' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(row_id) AS non_nulls,
  (COUNT(*) - COUNT(row_id)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.siebel.s_org_ext;

-- ── Task 2: null_analysis | s_org_ext.ou_num ──────────────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_02_null_analysis__s_org_ext_ou_num.csv
SELECT
  'ou_num' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(ou_num) AS non_nulls,
  (COUNT(*) - COUNT(ou_num)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.siebel.s_org_ext;

-- ── Task 3: null_analysis | s_org_ext.market_class_cd ─────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_03_null_analysis__s_org_ext_market_class_cd.csv
SELECT
  'market_class_cd' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(market_class_cd) AS non_nulls,
  (COUNT(*) - COUNT(market_class_cd)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.siebel.s_org_ext;

-- ── Task 4: null_analysis | s_org_ext.market_type_cd ──────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_04_null_analysis__s_org_ext_market_type_cd.csv
SELECT
  'market_type_cd' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(market_type_cd) AS non_nulls,
  (COUNT(*) - COUNT(market_type_cd)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.siebel.s_org_ext;

-- ── Task 5: null_analysis | account.Id ────────────────────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_05_null_analysis__account_Id.csv
SELECT
  'Id' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(Id) AS non_nulls,
  (COUNT(*) - COUNT(Id)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.salesforce_reports.account;

-- ── Task 6: null_analysis | account.customer_number_c ─────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_06_null_analysis__account_customer_number_c.csv
SELECT
  'customer_number_c' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(customer_number_c) AS non_nulls,
  (COUNT(*) - COUNT(customer_number_c)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.salesforce_reports.account;

-- ── Task 7: null_analysis | account.Type ──────────────────────
-- Business reason: Missing important data on key fields
-- Export this result as: task_07_null_analysis__account_Type.csv
SELECT
  'Type' AS column_name,
  COUNT(*) AS total_rows,
  COUNT(Type) AS non_nulls,
  (COUNT(*) - COUNT(Type)) / NULLIF(COUNT(*), 0) AS null_rate
FROM spark_ods.salesforce_reports.account;

-- ── Task 8: distribution_analysis | s_org_ext.market_class_cd ─
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_08_distribution_analysis__s_org_ext_market_.csv
SELECT market_class_cd AS value, COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext
GROUP BY market_class_cd
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 9: distribution_analysis | s_org_ext.market_type_cd ──
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_09_distribution_analysis__s_org_ext_market_.csv
SELECT market_type_cd AS value, COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext
GROUP BY market_type_cd
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 10: distribution_analysis | account.Type ──────────────
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_10_distribution_analysis__account_Type.csv
SELECT Type AS value, COUNT(*) AS frequency
FROM spark_ods.salesforce_reports.account
GROUP BY Type
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 11: segment_distribution | Siebel.market_class_cd ─────
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_11_segment_distribution__Siebel_market_clas.csv
SELECT market_class_cd AS value, COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext
GROUP BY market_class_cd
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 12: segment_distribution | Siebel.market_type_cd ──────
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_12_segment_distribution__Siebel_market_type.csv
SELECT market_type_cd AS value, COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext
GROUP BY market_type_cd
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 13: segment_distribution | Salesforce.Type ────────────
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_13_segment_distribution__Salesforce_Type.csv
SELECT Type AS value, COUNT(*) AS frequency
FROM spark_ods.salesforce_reports.account
GROUP BY Type
ORDER BY frequency DESC
LIMIT 50;

-- ── Task 14: segment_crosstab | Siebel.market_class_cd × Salesforce.Type ─
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_14_segment_crosstab__Siebel_market_class_cd.csv
SELECT
  a.market_class_cd  AS left_segment,
  b.Type AS right_segment,
  COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext a
JOIN spark_ods.salesforce_reports.account b
  ON a.ou_num = b.customer_number_c
GROUP BY 1, 2
ORDER BY frequency DESC
LIMIT 100;

-- ── Task 15: segment_crosstab | Siebel.market_type_cd × Salesforce.Type ─
-- Business reason: Look for all variations on customer segment — record type in Salesforce; market_class_cd and market_type_cd in Siebel
-- Export this result as: task_15_segment_crosstab__Siebel_market_type_cd_.csv
SELECT
  a.market_type_cd  AS left_segment,
  b.Type AS right_segment,
  COUNT(*) AS frequency
FROM spark_ods.siebel.s_org_ext a
JOIN spark_ods.salesforce_reports.account b
  ON a.ou_num = b.customer_number_c
GROUP BY 1, 2
ORDER BY frequency DESC
LIMIT 100;

-- ── Task 16: cross_system_overlap | ou_num = customer_number_c ─
-- Business reason: Customers which are present in both systems
-- Export this result as: task_16_cross_system_overlap__ou_num_=_customer_.csv
WITH l AS (
  SELECT DISTINCT ou_num AS k
  FROM spark_ods.siebel.s_org_ext
  WHERE ou_num IS NOT NULL
),
r AS (
  SELECT DISTINCT customer_number_c AS k
  FROM spark_ods.salesforce_reports.account
  WHERE customer_number_c IS NOT NULL
)
SELECT
  (SELECT COUNT(*) FROM l)                                  AS left_keys,
  (SELECT COUNT(*) FROM r)                                  AS right_keys,
  (SELECT COUNT(*) FROM l INNER JOIN r ON l.k = r.k)       AS in_both,
  (SELECT COUNT(*) FROM l LEFT  JOIN r ON l.k = r.k WHERE r.k IS NULL) AS left_only,
  (SELECT COUNT(*) FROM r LEFT  JOIN l ON r.k = l.k WHERE l.k IS NULL) AS right_only;

-- ── Task 17: join_analysis | s_org_ext → s_contact ─────────────
-- Business reason: Depth-1 discovery: link coverage for spark_ods.siebel.s_contact
-- Export this result as: task_17_join_analysis__s_org_ext_-_s_contact.csv
SELECT
  COUNT(*) AS total_records,
  COUNT(CASE WHEN EXISTS (
    SELECT 1 FROM spark_ods.siebel.s_contact b WHERE b.row_id = a.row_id
  ) THEN 1 END) AS matched_records,
  COUNT(CASE WHEN EXISTS (
    SELECT 1 FROM spark_ods.siebel.s_contact b WHERE b.row_id = a.row_id
  ) THEN 1 END) / NULLIF(COUNT(*), 0) AS match_rate
FROM spark_ods.siebel.s_org_ext a;
