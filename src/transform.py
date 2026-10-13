"""Transform stage: raw survey -> clean fact table + dimensions + audit trail.

Design principles
  * Raw data is never modified; every correction is logged in `dq_issue_log`.
  * Rows are flagged and excluded from analysis rather than silently deleted.
  * All thresholds come from config.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from .clean_demo import (check_experience_consistency, encode_bands, normalize_education,
                         normalize_gender, parse_race)
from .clean_geo import build_country_map, normalize_us_state
from .clean_money import apply_salary_rules, convert_to_usd, resolve_currency
from .clean_text import (UNCLASSIFIED, classify_title, normalize_industry, normalize_title)

RAW_COLS = [
    "timestamp", "how_old_are_you", "industry", "job_title", "additional_context_on_job_title",
    "annual_salary", "other_monetary_comp", "currency", "currency_other",
    "additional_context_on_income", "country", "state", "city",
    "overall_years_of_professional_experience", "years_of_experience_in_field",
    "highest_level_of_education_completed", "gender", "race",
]

_DOMESTIC_CURRENCY = {
    "United States": "USD", "United Kingdom": "GBP", "Canada": "CAD", "Australia": "AUD",
    "New Zealand": "NZD", "Germany": "EUR", "France": "EUR", "Ireland": "EUR",
    "Netherlands": "EUR", "Spain": "EUR", "Switzerland": "CHF", "Sweden": "SEK", "Japan": "JPY",
}


@dataclass
class TransformResult:
    raw: pd.DataFrame
    fact: pd.DataFrame
    country_map: pd.DataFrame
    industry_map: pd.DataFrame
    race_bridge: pd.DataFrame
    issues: pd.DataFrame
    dq_summary: pd.DataFrame
    before_after: dict = field(default_factory=dict)


def load_raw(path=C.RAW_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(RAW_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Source schema drift, missing columns: {sorted(missing)}")
    df = df[RAW_COLS].copy()
    df.insert(0, "row_id", np.arange(1, len(df) + 1))
    df["submitted_at"] = pd.to_datetime(df["timestamp"], format="%m/%d/%Y %H:%M:%S", errors="coerce")
    return df


def _flag_duplicates(raw: pd.DataFrame) -> pd.Series:
    """Identical answers (all fields except timestamp) re-submitted within DUPLICATE_MAX_GAP_HOURS."""
    key_cols = [c for c in RAW_COLS if c != "timestamp"]
    first_ts = raw.groupby(key_cols, dropna=False)["submitted_at"].transform("min")
    gap_h = (raw["submitted_at"] - first_ts).dt.total_seconds() / 3600
    # a re-submission is any later copy of the same answers inside the window
    # (ties at the exact same second: keep the lowest row_id)
    same_ts_later = (raw["submitted_at"] == first_ts) & raw.duplicated(key_cols, keep="first")
    return (((raw["submitted_at"] > first_ts) & (gap_h <= C.DUPLICATE_MAX_GAP_HOURS)) | same_ts_later)


def transform(raw: pd.DataFrame) -> TransformResult:
    n_raw = len(raw)
    df = raw.copy()
    issues: list[pd.DataFrame] = []
    catalogue: list[dict] = []

    def log(mask: pd.Series, rule_id: str, desc: str, severity: str, action: str, detail: pd.Series | None = None):
        mask = mask.fillna(False).astype(bool)
        n = int(mask.sum())
        catalogue.append({"rule_id": rule_id, "description": desc, "severity": severity,
                          "action": action, "n_rows": n, "pct_rows": round(100 * n / n_raw, 2)})
        if n:
            part = pd.DataFrame({"row_id": df.loc[mask, "row_id"].values, "rule_id": rule_id,
                                 "severity": severity, "action": action})
            part["detail"] = (detail.loc[mask].astype(str).values if detail is not None else "")
            issues.append(part)

    # 0. timestamp sanity -------------------------------------------------------------
    log(df["submitted_at"].isna(), "R00", "Unparseable timestamp", "high", "flag")

    # 1. duplicates -------------------------------------------------------------------
    df["is_duplicate"] = _flag_duplicates(df)
    log(df["is_duplicate"], "R01", "Re-submitted identical response (<=48h after first)", "high", "drop_from_analysis")

    # 2. geography --------------------------------------------------------------------
    cmap = build_country_map(df["country"])
    lookup = dict(zip(cmap["raw_value"].fillna("__nan__"), cmap["country_std"]))
    method = dict(zip(cmap["raw_value"].fillna("__nan__"), cmap["method"]))
    key = df["country"].fillna("__nan__")
    df["country_std"] = key.map(lookup)
    df["country_method"] = key.map(method)
    log(df["country_method"].isin(["fuzzy", "substring", "manual", "us_state_in_country"]), "R02",
        "Country repaired via fuzzy/substring/manual rule", "medium", "fix", df["country"])
    log(df["country_std"].eq("Unresolved"), "R03", "Country unresolved", "high", "drop_from_analysis", df["country"])

    is_us = df["country_std"].eq("United States")
    st = df["state"].map(normalize_us_state)
    df["state_std"] = np.where(is_us, st.map(lambda t: t[0]), "n/a (non-US)")
    state_flag = pd.Series(np.where(is_us, st.map(lambda t: t[1]), "n/a"), index=df.index)
    log(state_flag.eq("multi_state"), "R04", "US respondent lists several states -> 'Multiple states'", "low", "fix", df["state"])
    log(state_flag.eq("missing"), "R05", "US respondent without state -> 'Unknown'", "low", "fix")
    df["city_norm"] = (df["city"].fillna("").str.strip().str.replace(r"\s+", " ", regex=True).str.title()
                       .replace("", np.nan))

    # 3. currency & money -------------------------------------------------------------
    cur = [resolve_currency(c, o, k) for c, o, k in zip(df["currency"], df["currency_other"], df["country_std"])]
    df["currency_code"] = [c[0] for c in cur]
    df["currency_method"] = [c[1] for c in cur]
    log(df["currency_method"].isin(["text_alias", "iso_in_text", "iso_pattern", "country_disambiguated"]), "R06",
        "Currency recovered from 'Other' free text or AUD/NZD ambiguity", "medium", "fix", df["currency_other"])
    log(df["currency_code"].eq("UNKNOWN"), "R07", "Currency unresolved ('Other' without usable detail)", "high", "drop_from_analysis", df["currency_other"])

    df["salary_local"] = df["annual_salary"].astype(float)
    df["other_comp_local"] = df["other_monetary_comp"].astype(float)
    df["salary_usd"] = convert_to_usd(df["salary_local"], df["currency_code"])
    df = apply_salary_rules(df)
    reasons = {
        "zero_or_negative": ("R08a", "Salary is zero or negative"),
        "ambiguous_units_thousands_or_hourly": ("R08b", "Salary 1-999 in a major currency: thousands or hourly? (ambiguous)"),
        "below_usd_floor": ("R08c", f"Salary below USD {C.SALARY_USD_MIN:,}"),
        "above_usd_cap": ("R08d", f"Salary above USD {C.SALARY_USD_MAX:,}"),
    }
    for reason, (rid, desc) in reasons.items():
        log(df["salary_invalid_reason"].eq(reason), rid, desc, "high", "drop_from_analysis", df["salary_local"])
    log(df["other_comp_missing"], "R09", "Other compensation blank -> treated as 0", "low", "impute")
    log(df["other_comp_suspect"], "R10", f"Other compensation > {C.OTHER_COMP_TO_SALARY_MAX:.0f}x salary -> nulled", "medium", "fix", df["other_comp_local"])
    dom = df["country_std"].map(_DOMESTIC_CURRENCY)
    log(dom.notna() & (dom != df["currency_code"]) & df["currency_code"].ne("UNKNOWN"), "R16",
        "Currency differs from country's domestic currency (expat or mislabel)", "low", "flag")

    # 4. categorical text -------------------------------------------------------------
    ind = df["industry"].map(normalize_industry)
    df["industry_std"] = ind.map(lambda t: t[0])
    df["industry_method"] = ind.map(lambda t: t[1])
    log(df["industry_method"].isin(["synonym", "keyword"]), "R13", "Free-text industry mapped to a standard category", "medium", "fix", df["industry"])
    log(df["industry_std"].eq(UNCLASSIFIED), "R14", "Industry unclassified/missing", "low", "flag", df["industry"])

    df["job_title_norm"] = df["job_title"].map(normalize_title)
    cls = df["job_title_norm"].map(classify_title)
    df["seniority"] = cls.map(lambda t: t[0])
    df["job_family"] = cls.map(lambda t: t[1])
    df["is_data_role"] = cls.map(lambda t: t[2])
    log(df["job_family"].eq("Other"), "R15", "Job title not mapped to a job family", "low", "flag", df["job_title"])

    # 5. demographics & experience ----------------------------------------------------
    age = encode_bands(df["how_old_are_you"], C.AGE_BANDS)
    exp_all = encode_bands(df["overall_years_of_professional_experience"], C.EXPERIENCE_BANDS)
    exp_fld = encode_bands(df["years_of_experience_in_field"], C.EXPERIENCE_BANDS)
    chk = check_experience_consistency(age, exp_all, exp_fld)
    df["age_mid"] = age["mid"]
    df["exp_overall_ord"], df["exp_overall_years"] = exp_all["ord"], exp_all["mid"]
    df["exp_field_ord"] = np.minimum(exp_fld["ord"], exp_all["ord"])
    df["exp_field_years"] = chk["field_exp_years_fixed"]
    df["field_gt_overall"], df["age_exp_impossible"] = chk["field_gt_overall"], chk["age_exp_impossible"]
    log(df["field_gt_overall"], "R11", "Years in field > total years -> capped at total years", "medium", "fix")
    log(df["age_exp_impossible"], "R12", "Age band incompatible with experience band", "high", "drop_from_analysis")

    df["education_std"] = df["highest_level_of_education_completed"].map(normalize_education)
    df["education_rank"] = df["education_std"].map(C.EDUCATION_LEVELS)
    df["gender_std"] = df["gender"].map(normalize_gender)
    log(df["education_std"].eq("Unknown"), "R17", "Education missing -> 'Unknown'", "low", "fix")
    log(df["gender_std"].eq("Unknown"), "R18", "Gender missing -> 'Unknown'", "low", "fix")

    races = df["race"].map(parse_race)
    race_bridge = (pd.DataFrame({"row_id": df["row_id"], "race_option": races})
                   .explode("race_option").dropna(subset=["race_option"]).reset_index(drop=True))

    # 6. analysis-ready gate ----------------------------------------------------------
    df["is_analysis_ready"] = (
        ~df["is_duplicate"] & df["is_salary_valid"] & df["country_std"].ne("Unresolved")
        & ~df["age_exp_impossible"] & df["submitted_at"].notna()
    )
    log(~df["is_analysis_ready"], "R99", "Row excluded from analysis (any blocking rule)", "info", "summary")

    # 7. industry audit map -----------------------------------------------------------
    imap = (df.groupby(["industry", "industry_std", "industry_method"], dropna=False)
              .size().reset_index(name="n_rows")
              .rename(columns={"industry": "raw_value", "industry_method": "method"}))

    fact_cols = [
        "row_id", "submitted_at", "age_mid", "how_old_are_you", "education_std", "education_rank", "gender_std",
        "country_std", "country_method", "state_std", "city_norm", "industry_std", "industry_method",
        "job_title_norm", "seniority", "job_family", "is_data_role",
        "overall_years_of_professional_experience", "exp_overall_ord", "exp_overall_years",
        "years_of_experience_in_field", "exp_field_ord", "exp_field_years",
        "currency_code", "currency_method", "salary_local", "other_comp_local_clean",
        "salary_usd", "other_comp_usd", "total_comp_usd", "other_comp_missing",
        "is_duplicate", "is_salary_valid", "salary_invalid_reason", "field_gt_overall",
        "age_exp_impossible", "is_analysis_ready",
    ]
    fact = df[fact_cols].rename(columns={
        "how_old_are_you": "age_band",
        "overall_years_of_professional_experience": "exp_overall_band",
        "years_of_experience_in_field": "exp_field_band",
        "other_comp_local_clean": "other_comp_local",
    })

    ready = fact[fact["is_analysis_ready"]]
    before_after = {
        "rows_raw": n_raw,
        "rows_duplicate": int(df["is_duplicate"].sum()),
        "rows_salary_invalid": int((~df["is_salary_valid"]).sum()),
        "rows_analysis_ready": int(len(ready)),
        "country_distinct_raw": int(raw["country"].nunique(dropna=True)),
        "country_distinct_clean": int(df.loc[df["country_std"].ne("Unresolved"), "country_std"].nunique()),
        "country_unresolved_rows": int(df["country_std"].eq("Unresolved").sum()),
        "industry_distinct_raw": int(raw["industry"].nunique(dropna=True)),
        "industry_distinct_clean": int(df["industry_std"].nunique()),
        "industry_unclassified_rows": int(df["industry_std"].eq(UNCLASSIFIED).sum()),
        "currency_labels_raw": int(raw["currency"].nunique()),
        "currency_codes_clean": int(df.loc[df["currency_code"].ne("UNKNOWN"), "currency_code"].nunique()),
        "job_title_distinct_raw": int(raw["job_title"].nunique()),
        "job_title_distinct_norm": int(df["job_title_norm"].nunique()),
        "job_family_other_pct": round(100 * float(df["job_family"].eq("Other").mean()), 1),
        "salary_raw_mean": float(raw["annual_salary"].mean()),
        "salary_raw_max": float(raw["annual_salary"].max()),
        "salary_raw_min": float(raw["annual_salary"].min()),
        "salary_usd_clean_mean": float(ready["salary_usd"].mean()),
        "salary_usd_clean_median": float(ready["salary_usd"].median()),
        "salary_usd_clean_max": float(ready["salary_usd"].max()),
        "salary_usd_clean_min": float(ready["salary_usd"].min()),
        "us_rows_ready": int((ready["country_std"] == "United States").sum()),
    }

    issue_log = pd.concat(issues, ignore_index=True) if issues else pd.DataFrame(
        columns=["row_id", "rule_id", "severity", "action", "detail"])
    return TransformResult(raw=raw, fact=fact, country_map=cmap, industry_map=imap,
                           race_bridge=race_bridge, issues=issue_log,
                           dq_summary=pd.DataFrame(catalogue), before_after=before_after)
