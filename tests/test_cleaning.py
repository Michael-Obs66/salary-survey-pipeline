"""Unit tests for the cleansing rules. Run: pytest -q"""
import hashlib

import numpy as np
import pandas as pd
import pytest

from src import config as C
from src.clean_demo import check_experience_consistency, encode_bands, parse_race
from src.clean_geo import normalize_country, normalize_us_state
from src.clean_money import apply_salary_rules, convert_to_usd, resolve_currency
from src.clean_text import classify_title, normalize_industry, normalize_title
from src.transform import load_raw, transform


@pytest.mark.parametrize("raw,expected", [
    ("USA", "United States"), ("U.S.", "United States"), ("united states of america", "United States"),
    ("Unites States", "United States"), ("Unitef Stated", "United States"), ("America", "United States"),
    ("UK", "United Kingdom"), ("England", "United Kingdom"), ("Scotland, UK", "United Kingdom"),
    ("Canda", "Canada"), ("Nederland", "Netherlands"), ("Russia", "Russia"), ("Turkey", "Turkey"),
    ("California", "United States"), ("From New Zealand but on projects across APAC", "New Zealand"),
])
def test_country_resolution(raw, expected):
    assert normalize_country(raw)[0] == expected


@pytest.mark.parametrize("raw", ["Y", "Remote", "Global", "UXZ", None, float("nan"), ""])
def test_country_unresolved_is_never_guessed(raw):
    assert normalize_country(raw)[0] == "Unresolved"


def test_us_state_cases():
    assert normalize_us_state("California") == ("California", "ok")
    assert normalize_us_state("Californa")[0] == "California"            # typo
    assert normalize_us_state("California, New York") == ("Multiple states", "multi_state")
    assert normalize_us_state(None) == ("Unknown", "missing")
    assert normalize_us_state("District of Columbia")[0] == "District of Columbia"


def test_currency_resolution():
    assert resolve_currency("AUD/NZD", None, "New Zealand")[0] == "NZD"
    assert resolve_currency("AUD/NZD", None, "Australia")[0] == "AUD"
    assert resolve_currency("Other", "Canadian", "Canada")[0] == "CAD"
    assert resolve_currency("Other", "BRL (R$)", "Brazil")[0] == "BRL"
    assert resolve_currency("Other", "MXN", "Mexico")[0] == "MXN"
    assert resolve_currency("Other", None, "Brazil")[0] == "UNKNOWN"
    assert resolve_currency("Other", "RSU / equity", "United States")[0] == "UNKNOWN"
    assert resolve_currency("USD", None, "United States")[0] == "USD"


def _money_frame(salary, cur="USD", omc=0.0):
    df = pd.DataFrame({"salary_local": [float(salary)], "other_comp_local": [omc], "currency_code": [cur]})
    df["salary_usd"] = convert_to_usd(df["salary_local"], df["currency_code"])
    return apply_salary_rules(df).iloc[0]


@pytest.mark.parametrize("salary,reason", [
    (0, "zero_or_negative"), (130, "ambiguous_units_thousands_or_hourly"), (5_000, "below_usd_floor"),
    (102_000_000, "above_usd_cap"), (2_000_000, "above_usd_cap"),
])
def test_invalid_salary_reasons(salary, reason):
    r = _money_frame(salary)
    assert not r["is_salary_valid"] and r["salary_invalid_reason"] == reason


def test_valid_salary_and_other_comp_rules():
    assert _money_frame(75_000)["is_salary_valid"]
    assert _money_frame(5_000_000, "JPY")["is_salary_valid"]            # ~USD 46k after FX
    r = _money_frame(60_000, omc=1_000_000)                              # bonus > 5x salary
    assert r["other_comp_suspect"] and r["total_comp_usd"] == 60_000


def test_industry_mapping():
    assert normalize_industry("Computing or Tech") == ("Computing or Tech", "exact")
    assert normalize_industry("Public Libraries")[0] == "Libraries & Archives"
    assert normalize_industry("Biotechnology")[0] == "Biotech & Pharma"
    assert normalize_industry("Automotive technician")[0] != "Computing or Tech"   # 'tech' must not match 'technician'
    assert normalize_industry("Academic publishing")[0] == "Publishing"
    assert normalize_industry(None)[1] == "missing"
    assert normalize_industry("zzzz qqqq")[1] == "unclassified"


def test_title_classification():
    assert normalize_title("  Senior  Software-Engineer!! ") == "senior software engineer"
    s, f, d = classify_title("senior data scientist")
    assert (s, f, d) == ("Senior", "Data & Analytics", True)
    assert classify_title("director of operations")[0] == "Director"
    assert classify_title("registered nurse")[1] == "Healthcare & Clinical"


def test_race_multiselect_is_not_split_on_commas():
    got = parse_race("Hispanic, Latino, or Spanish origin, White")
    assert got == ["Hispanic, Latino, or Spanish origin", "White"]
    assert parse_race(None) == []


def test_experience_consistency():
    age = encode_bands(pd.Series(["18-24", "35-44"]), C.AGE_BANDS)
    overall = encode_bands(pd.Series(["21 - 30 years", "11 - 20 years"]), C.EXPERIENCE_BANDS)
    field = encode_bands(pd.Series(["21 - 30 years", "21 - 30 years"]), C.EXPERIENCE_BANDS)
    chk = check_experience_consistency(age, overall, field)
    assert chk["age_exp_impossible"].tolist() == [True, False]           # 18-24 with 21+ years is impossible
    assert chk["field_gt_overall"].tolist() == [False, True]
    assert chk["field_exp_years_fixed"].iloc[1] == overall["mid"].iloc[1]


@pytest.fixture(scope="module")
def result():
    return transform(load_raw())


def test_pipeline_row_conservation_and_invariants(result):
    f = result.fact
    assert len(f) == len(result.raw) and f["row_id"].is_unique
    ready = f[f["is_analysis_ready"]]
    assert ready["salary_usd"].between(C.SALARY_USD_MIN, C.SALARY_USD_MAX).all()
    assert not ready["is_duplicate"].any()
    assert (ready["exp_field_ord"] <= ready["exp_overall_ord"]).all()
    assert (ready["total_comp_usd"] >= ready["salary_usd"] - 0.01).all()


def test_pipeline_is_deterministic(result):
    again = transform(load_raw())
    h = lambda d: hashlib.sha256(pd.util.hash_pandas_object(d, index=True).values.tobytes()).hexdigest()
    assert h(result.fact.drop(columns=["submitted_at"])) == h(again.fact.drop(columns=["submitted_at"]))


def test_duplicates_are_only_later_copies(result):
    dup = result.fact[result.fact["is_duplicate"]]
    assert len(dup) > 0
    raw = result.raw.set_index("row_id")
    cols = [c for c in raw.columns if c not in ("timestamp", "submitted_at")]
    for rid in dup["row_id"].head(25):                                   # each dropped row has an earlier twin
        r = raw.loc[rid]
        twins = raw[(raw[cols].fillna("~") == r[cols].fillna("~")).all(axis=1) & (raw["submitted_at"] <= r["submitted_at"])]
        assert len(twins) >= 2
