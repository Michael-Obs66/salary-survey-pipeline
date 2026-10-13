"""Inference helper: estimate a US salary range from a profile.

    python -m src.predict
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from . import config as C
from .clean_text import classify_title, normalize_title


def predict_salary(*, job_title: str, industry_std: str, state_std: str, exp_overall_years: float,
                   exp_field_years: float, age_mid: float, education_std: str) -> dict:
    bundle = joblib.load(C.ROOT / "models" / "salary_model.joblib")
    title = normalize_title(job_title)
    seniority, family, is_data = classify_title(title)
    row = pd.DataFrame([{
        "exp_overall_years": exp_overall_years, "exp_field_years": min(exp_field_years, exp_overall_years),
        "age_mid": age_mid, "is_data_role": int(is_data), "education_std": education_std,
        "industry_std": industry_std, "job_family": family, "seniority": seniority,
        "state_std": state_std, "job_title_norm": title}])[bundle["features"]]
    point = float(np.exp(bundle["point"].predict(row)[0]))
    lo = float(np.exp(bundle["q10"].predict(row)[0] - bundle["qhat_log"]))
    hi = float(np.exp(bundle["q90"].predict(row)[0] + bundle["qhat_log"]))
    return {"estimate_usd": round(point, -2), "range_80pct_usd": (round(min(lo, point), -2), round(max(hi, point), -2)),
            "parsed": {"seniority": seniority, "job_family": family}}


if __name__ == "__main__":
    print(predict_salary(job_title="Senior Data Scientist", industry_std="Computing or Tech", state_std="Texas",
                         exp_overall_years=9, exp_field_years=6, age_mid=34.5, education_std="Master's degree"))
