"""One command, whole pipeline:  python -m src.run_pipeline

extract -> transform -> load (SQLite) -> quality gates -> SQL analytics -> model -> figures
"""
from __future__ import annotations

import sys
import time

from . import config as C
from .figures import make_all
from .load import load
from .model import run_modeling
from .quality import run_checks, write_report
from .run_sql import run_all
from .transform import load_raw, transform


def main(skip_model: bool = False) -> int:
    t0 = time.time()
    print("[1/6] extract");   raw = load_raw();             print(f"      {len(raw):,} raw rows")
    print("[2/6] transform"); res = transform(raw);          print(f"      {res.before_after['rows_analysis_ready']:,} analysis-ready")
    print("[3/6] load");      con = load(res);               print(f"      warehouse -> {C.DB_PATH.name}")
    print("[4/6] quality gates")
    checks = run_checks(con); write_report(checks, res.dq_summary, res.before_after)
    failed = checks[checks.status == "FAIL"]
    print(f"      {len(checks) - len(failed)}/{len(checks)} PASS")
    if len(failed):
        print(failed.to_string(index=False)); return 1
    print("[5/6] SQL analytics"); sql = run_all(con);        print(f"      {len(sql)} queries executed")
    if skip_model:
        return 0
    print("[6/6] model + figures")
    metrics = run_modeling(con)
    make_all(con, sql, metrics, res.before_after)
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(skip_model="--skip-model" in sys.argv))
