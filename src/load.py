"""Load stage: write raw + clean layers into SQLite (idempotent: schema is dropped/recreated)."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from . import config as C
from .transform import RAW_COLS, TransformResult


def _bool_to_int(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == bool or str(out[col].dtype) == "boolean":
            out[col] = out[col].astype(int)
    return out


def _dim(values: pd.Series, id_col: str, name_col: str) -> pd.DataFrame:
    uniq = sorted(values.dropna().unique())
    return pd.DataFrame({id_col: range(1, len(uniq) + 1), name_col: uniq})


def load(res: TransformResult, db_path=C.DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript((C.SQL_DIR / "schema.sql").read_text())

    # raw layer
    raw = res.raw[["row_id"] + [c for c in RAW_COLS]].copy()
    raw.to_sql("raw_survey", con, if_exists="append", index=False)

    # dimensions
    d_country = _dim(res.fact["country_std"], "country_id", "country_std")
    d_industry = _dim(res.fact["industry_std"], "industry_id", "industry_std")
    d_family = _dim(res.fact["job_family"], "job_family_id", "job_family")
    d_country.to_sql("dim_country", con, if_exists="append", index=False)
    d_industry.to_sql("dim_industry", con, if_exists="append", index=False)
    d_family.to_sql("dim_job_family", con, if_exists="append", index=False)

    codes = sorted(set(res.fact["currency_code"]) | set(C.FX_TO_USD))
    pd.DataFrame({
        "currency_code": codes,
        "usd_per_unit": [C.FX_TO_USD.get(c, np.nan) for c in codes],
        "fx_note": ["approx. mid-May-2021 snapshot; descriptive use only" if c in C.FX_TO_USD
                    else "unresolved currency" for c in codes],
    }).to_sql("dim_currency", con, if_exists="append", index=False)

    # audit tables
    res.country_map.to_sql("map_country_raw", con, if_exists="append", index=False)
    res.industry_map.to_sql("map_industry_raw", con, if_exists="append", index=False)
    res.issues.to_sql("dq_issue_log", con, if_exists="append", index=False)
    res.dq_summary.to_sql("dq_summary", con, if_exists="append", index=False)

    # fact
    f = res.fact.merge(d_country, on="country_std").merge(d_industry, on="industry_std") \
                .merge(d_family, on="job_family")
    f = f.drop(columns=["country_std", "industry_std", "job_family"]).sort_values("row_id")
    f["submitted_at"] = f["submitted_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    f = _bool_to_int(f)
    cols = [r[1] for r in con.execute("PRAGMA table_info(fact_response)")]
    f[cols].to_sql("fact_response", con, if_exists="append", index=False)

    res.race_bridge.drop_duplicates().to_sql("bridge_response_race", con, if_exists="append", index=False)
    con.commit()
    return con
