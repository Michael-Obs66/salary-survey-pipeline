"""Currency resolution, USD conversion, and salary validity rules."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pycountry

from . import config as C

_ISO = {c.alpha_3 for c in pycountry.currencies}


def resolve_currency(currency: str, currency_other, country_std: str) -> tuple[str, str]:
    """Return (currency_code, method).

    - 'AUD/NZD' is ambiguous in the form -> disambiguated by country.
    - 'Other' + free text in `currency_other` -> alias table / ISO code / pattern.
    - Anything we cannot trust -> 'UNKNOWN' (row keeps local salary but gets no USD value).
    """
    cur = str(currency).strip().upper()
    if cur == "AUD/NZD":
        return ("NZD" if country_std == "New Zealand" else "AUD"), "country_disambiguated"
    if cur != "OTHER":
        return cur, "as_reported"
    if currency_other is None or (isinstance(currency_other, float) and pd.isna(currency_other)):
        return "UNKNOWN", "other_without_detail"
    txt = str(currency_other).strip().upper()
    if txt in C.CURRENCY_TEXT_ALIASES:
        return C.CURRENCY_TEXT_ALIASES[txt], "text_alias"
    if txt in C.FX_TO_USD:
        return txt, "iso_in_text"
    m = re.search(r"\b([A-Z]{3})\b", txt)
    if m and m.group(1) in C.FX_TO_USD:
        return m.group(1), "iso_pattern"
    return "UNKNOWN", "unparseable"


def convert_to_usd(amount: pd.Series, code: pd.Series) -> pd.Series:
    rate = code.map(C.FX_TO_USD)
    return amount * rate


def apply_salary_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Add salary-validity columns. Rules are ordered and the FIRST failing rule is the reason."""
    out = df.copy()
    reason = pd.Series("", index=out.index, dtype="object")

    def mark(mask: pd.Series, label: str) -> None:
        nonlocal reason
        reason = reason.mask(mask & (reason == ""), label)

    sal = out["salary_local"]
    mark(sal <= 0, "zero_or_negative")
    mark(out["currency_code"].eq("UNKNOWN"), "currency_unresolved")
    ambiguous = sal.between(1, C.AMBIGUOUS_UNIT_MAX_LOCAL) & out["currency_code"].isin(
        ["USD", "CAD", "GBP", "EUR", "AUD", "NZD", "CHF"]
    )
    mark(ambiguous, "ambiguous_units_thousands_or_hourly")
    mark(out["salary_usd"] < C.SALARY_USD_MIN, "below_usd_floor")
    mark(out["salary_usd"] > C.SALARY_USD_MAX, "above_usd_cap")
    out["salary_invalid_reason"] = reason.replace("", np.nan)
    out["is_salary_valid"] = out["salary_invalid_reason"].isna()

    # other compensation: missing -> treated as 0 but remembered; absurd -> NaN
    omc = out["other_comp_local"]
    out["other_comp_missing"] = omc.isna()
    bad_omc = omc > C.OTHER_COMP_TO_SALARY_MAX * sal.clip(lower=1)
    out["other_comp_suspect"] = bad_omc.fillna(False)
    omc_clean = omc.mask(out["other_comp_suspect"])
    out["other_comp_local_clean"] = omc_clean.fillna(0.0)
    out["other_comp_usd"] = convert_to_usd(out["other_comp_local_clean"], out["currency_code"])
    out["total_comp_usd"] = out["salary_usd"] + out["other_comp_usd"]
    return out
