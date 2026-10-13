"""Country and US-state standardisation.

Strategy for `country` (294 raw spellings in the source):
  1. manual override   (sentences typed into the field, hand-checked)
  2. exact alias       (USA / U.S. / UK ...)
  3. exact name        (pycountry names, official names, ISO3)
  4. fuzzy match       (difflib, handles 'Unites States', 'Unitef Stated')
  5. substring search  (earliest country mention in a long free-text answer)
  6. unresolved        (kept, flagged, never silently guessed)
Each decision is recorded in `method` so the mapping is auditable.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import pandas as pd
import pycountry

from . import config as C


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _display(name: str) -> str:
    return C.COUNTRY_DISPLAY_OVERRIDES.get(name, name)


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for c in pycountry.countries:
        disp = _display(c.name)
        for attr in ("name", "official_name", "common_name"):
            v = getattr(c, attr, None)
            if v:
                lookup[_norm(v)] = disp
        lookup[_norm(c.alpha_3)] = disp
    for disp in set(lookup.values()):          # 'Russia', 'Turkey', 'Vietnam' ... as people actually type them
        lookup[_norm(disp)] = disp
    for k, v in C.COUNTRY_ALIASES.items():
        lookup[_norm(k)] = v
    # a handful of alias targets are not pycountry short names
    lookup[_norm("United States of America")] = "United States"
    return lookup


_LOOKUP = _build_lookup()
_FUZZY_KEYS = [k for k in _LOOKUP if len(k) >= 5]
_SUBSTR_KEYS = sorted([k for k in _LOOKUP if len(k) >= 4 or k in ("us", "usa", "uk")], key=len, reverse=True)
_STATE_NORM = {_norm(s): s for s in C.US_STATES + C.US_STATE_OTHER}


def normalize_country(raw) -> tuple[str, str]:
    """Return (country_std, method). Never raises; unresolved values are labelled."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "Unresolved", "missing"
    key = _norm(raw)
    if not key:
        return "Unresolved", "missing"
    if key in C.COUNTRY_MANUAL_OVERRIDES:
        return C.COUNTRY_MANUAL_OVERRIDES[key], "manual"
    if key in C.COUNTRY_ALIASES:
        return C.COUNTRY_ALIASES[key], "alias"
    if key in _LOOKUP:
        return _LOOKUP[key], "exact"
    if key in _STATE_NORM:                       # 'California' typed in the country box
        return "United States", "us_state_in_country"
    if len(key) >= 5:
        hit = difflib.get_close_matches(key, _FUZZY_KEYS, n=1, cutoff=0.8)
        if hit:
            return _LOOKUP[hit[0]], "fuzzy"
    # longer free-text answers: take the earliest country mention
    best = None
    for k in _SUBSTR_KEYS:
        m = re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", key)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), _LOOKUP[k])
    if best and (len(key) > 6 or " " in key):
        return best[1], "substring"
    return "Unresolved", "unresolved"


def build_country_map(raw_values: pd.Series) -> pd.DataFrame:
    """Audit table: every distinct raw spelling -> standard name + method + row count."""
    counts = raw_values.value_counts(dropna=False)
    rows = []
    for raw, n in counts.items():
        std, method = normalize_country(raw)
        rows.append({"raw_value": raw, "country_std": std, "method": method, "n_rows": int(n)})
    return pd.DataFrame(rows)


def normalize_us_state(raw) -> tuple[str, str]:
    """Return (state_std, flag). Only meaningful when country_std == United States."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or not str(raw).strip():
        return "Unknown", "missing"
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    # 'District of Columbia' is the only valid name containing no comma; multi-state has commas
    resolved = []
    for p in parts:
        k = _norm(p)
        if k in _STATE_NORM:
            resolved.append(_STATE_NORM[k])
        else:
            hit = difflib.get_close_matches(k, list(_STATE_NORM), n=1, cutoff=0.85)
            resolved.append(_STATE_NORM[hit[0]] if hit else None)
    resolved = [r for r in resolved if r]
    if not resolved:
        return "Unknown", "unparseable"
    if len(set(resolved)) > 1:
        return "Multiple states", "multi_state"
    return resolved[0], "ok"
