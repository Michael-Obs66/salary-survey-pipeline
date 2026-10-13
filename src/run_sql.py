"""Execute every sql/analysis/*.sql against the warehouse and save results as CSV."""
from __future__ import annotations

import sqlite3

import pandas as pd

from . import config as C


def run_all(con: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    out_dir = C.REPORT_DIR / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, pd.DataFrame] = {}
    for path in sorted((C.SQL_DIR / "analysis").glob("*.sql")):
        df = pd.read_sql_query(path.read_text(), con)
        df.to_csv(out_dir / f"{path.stem}.csv", index=False)
        results[path.stem] = df
    return results
