"""Demographic / experience cleaning: ordinal encoding, logical-consistency checks, multi-select parsing."""
from __future__ import annotations

import pandas as pd

from . import config as C


def encode_bands(series: pd.Series, table: dict) -> pd.DataFrame:
    """Map a labelled band to ordinal, midpoint, low, high. Unknown labels -> NaN (and are reported)."""
    ord_ = series.map(lambda x: table.get(x, (None,) * 4)[0])
    mid = series.map(lambda x: table.get(x, (None,) * 4)[1])
    low = series.map(lambda x: table.get(x, (None,) * 4)[2])
    high = series.map(lambda x: table.get(x, (None,) * 4)[3])
    return pd.DataFrame({"ord": ord_, "mid": mid, "low": low, "high": high}, index=series.index)


def check_experience_consistency(age: pd.DataFrame, overall: pd.DataFrame, field: pd.DataFrame) -> pd.DataFrame:
    """Logical checks across three answers that must agree with each other.

    field_gt_overall : years in field cannot exceed total professional years  (fixed by capping)
    age_exp_impossible: lowest possible experience > (oldest possible age - 14)  (flagged, kept)
    """
    field_gt_overall = field["ord"] > overall["ord"]
    age_exp_impossible = overall["low"] > (age["high"] - C.MIN_WORKING_AGE)
    field_fixed = field["mid"].where(~field_gt_overall, overall["mid"])
    return pd.DataFrame(
        {
            "field_gt_overall": field_gt_overall,
            "age_exp_impossible": age_exp_impossible,
            "field_exp_years_fixed": field_fixed,
        },
        index=age.index,
    )


def normalize_gender(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unknown"
    txt = str(raw).strip()
    if txt.lower() in {"prefer not to answer", "other or prefer not to answer"}:
        return "Other / prefer not to answer"
    return txt


def normalize_education(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or not str(raw).strip():
        return "Unknown"
    return str(raw).strip()


def parse_race(raw) -> list[str]:
    """Multi-select answer -> list of options.

    A naive `split(',')` would shred 'Hispanic, Latino, or Spanish origin' into three bogus
    categories, so we match against the known option strings instead.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    txt = str(raw)
    found = [opt for opt in C.RACE_OPTIONS if opt in txt]
    return found
