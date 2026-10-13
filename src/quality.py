"""Post-load data-quality gates. The pipeline fails loudly if any gate breaks."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

from . import config as C

ALLOWED_SENIORITY = ("Executive", "Director", "Manager", "Lead / Principal", "Senior",
                     "Junior / Entry", "Mid-level / Unspecified")


def _scalar(con: sqlite3.Connection, sql: str):
    return con.execute(sql).fetchone()[0]


def run_checks(con: sqlite3.Connection) -> pd.DataFrame:
    n_raw = _scalar(con, "SELECT COUNT(*) FROM raw_survey")
    rows = []

    def check(cid: str, desc: str, observed, expected, op: str = "=="):
        ok = {"==": observed == expected, "<=": observed <= expected, ">=": observed >= expected}[op]
        rows.append({"check_id": cid, "description": desc, "observed": observed,
                     "expected": f"{op} {expected}", "status": "PASS" if ok else "FAIL"})

    # --- integrity -----------------------------------------------------------------------------
    check("Q01", "Row reconciliation: fact_response == raw_survey",
          _scalar(con, "SELECT COUNT(*) FROM fact_response"), n_raw)
    check("Q02", "No orphan foreign keys", len(con.execute("PRAGMA foreign_key_check").fetchall()), 0)
    check("Q03", "Primary key unique in fact_response",
          _scalar(con, "SELECT COUNT(*)-COUNT(DISTINCT row_id) FROM fact_response"), 0)
    check("Q04", "Every country_std in dim_country is unique",
          _scalar(con, "SELECT COUNT(*)-COUNT(DISTINCT country_std) FROM dim_country"), 0)

    # --- analysis-ready invariants ------------------------------------------------------------------
    check("Q05", "Ready rows have salary_usd within [floor, cap]",
          _scalar(con, f"""SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1
                          AND (salary_usd IS NULL OR salary_usd < {C.SALARY_USD_MIN} OR salary_usd > {C.SALARY_USD_MAX})"""), 0)
    check("Q06", "Ready rows are never duplicates / invalid / impossible-age",
          _scalar(con, """SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1
                          AND (is_duplicate=1 OR is_salary_valid=0 OR age_exp_impossible=1)"""), 0)
    check("Q07", "Ready rows have a resolved currency",
          _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1 AND currency_code='UNKNOWN'"), 0)
    check("Q08", "Ready rows: years in field <= total years (after repair)",
          _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1 AND exp_field_ord > exp_overall_ord"), 0)
    check("Q09", "Ready rows: total_comp_usd >= salary_usd",
          _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1 AND total_comp_usd < salary_usd - 0.01"), 0)
    check("Q10", "Dropped duplicates all excluded from analysis",
          _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE is_duplicate=1 AND is_analysis_ready=1"), 0)

    # --- domain / value checks -----------------------------------------------------------------------------
    allowed = ",".join(f"'{s}'" for s in ALLOWED_SENIORITY)
    check("Q11", "Seniority only takes allowed values",
          _scalar(con, f"SELECT COUNT(*) FROM fact_response WHERE seniority NOT IN ({allowed})"), 0)
    check("Q12", "Survey timestamps inside the collection window (2021-04-27..2021-05-17)",
          _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE submitted_at < '2021-04-27' OR submitted_at > '2021-05-18'"), 0)
    check("Q13", "No placeholder state for US ready rows other than Unknown/Multiple",
          _scalar(con, """SELECT COUNT(*) FROM vw_analysis WHERE country_std='United States'
                          AND state_std LIKE '%,%'"""), 0)
    check("Q14", "Multi-select race options parsed with no comma fragments",
          _scalar(con, """SELECT COUNT(*) FROM bridge_response_race
                          WHERE race_option IN ('Latino','Hispanic','Latino, or Spanish origin','or Spanish origin')"""), 0)

    # --- coverage gates (cleansing quality thresholds) --------------------------------------------------
    unresolved_pct = 100 * _scalar(con, "SELECT COUNT(*) FROM fact_response f JOIN dim_country c USING(country_id) WHERE c.country_std='Unresolved'") / n_raw
    check("Q15", "Country unresolved rows <= 0.5%", round(unresolved_pct, 3), 0.5, "<=")
    unclassified_pct = 100 * _scalar(con, "SELECT COUNT(*) FROM fact_response f JOIN dim_industry i USING(industry_id) WHERE i.industry_std='Other / Unclassified'") / n_raw
    check("Q16", "Industry unclassified rows <= 2%", round(unclassified_pct, 3), 2.0, "<=")
    other_fam_pct = 100 * _scalar(con, "SELECT COUNT(*) FROM fact_response f JOIN dim_job_family j USING(job_family_id) WHERE j.job_family='Other'") / n_raw
    check("Q17", "Job family 'Other' <= 6%", round(other_fam_pct, 3), 6.0, "<=")
    ready_pct = 100 * _scalar(con, "SELECT COUNT(*) FROM fact_response WHERE is_analysis_ready=1") / n_raw
    check("Q18", "At least 97% of rows survive cleaning (not over-filtering)", round(ready_pct, 2), 97.0, ">=")
    return pd.DataFrame(rows)


def write_report(checks: pd.DataFrame, dq_summary: pd.DataFrame, before_after: dict) -> None:
    C.REPORT_DIR.mkdir(exist_ok=True)
    (C.REPORT_DIR / "dq_checks.json").write_text(json.dumps(
        {"before_after": before_after, "checks": checks.to_dict("records")}, indent=2, default=str))
    lines = ["# Data Quality Report", "",
             f"Gates: **{(checks.status == 'PASS').sum()}/{len(checks)} PASS**", "",
             "## Validation gates (post-load, run against the SQLite warehouse)", "",
             "| ID | Check | Observed | Expected | Status |", "|---|---|---|---|---|"]
    for r in checks.itertuples():
        lines.append(f"| {r.check_id} | {r.description} | {r.observed} | {r.expected} | {r.status} |")
    lines += ["", "## Cleansing rules fired (audit catalogue)", "",
              "| Rule | Description | Severity | Action | Rows | % |", "|---|---|---|---|---:|---:|"]
    for r in dq_summary.sort_values("rule_id").itertuples():
        lines.append(f"| {r.rule_id} | {r.description} | {r.severity} | {r.action} | {r.n_rows:,} | {r.pct_rows} |")
    (C.REPORT_DIR / "data_quality_report.md").write_text("\n".join(lines) + "\n")
