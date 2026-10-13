"""Salary model for US respondents (log-salary regression) with honest evaluation.

Design choices (each one documented in the README):
  * US + USD only  -> no FX / purchasing-power noise leaks into the target.
  * gender and race are NOT features (protected attributes); they are used only for the residual audit.
  * other_comp / total_comp are NOT features (outcome-adjacent, would leak).
  * 80/20 split; model selection by 5-fold CV on the 80% only; holdout touched once at the end.
  * Prediction intervals via conformalised quantile regression (CQR) -> finite-sample coverage.
"""
from __future__ import annotations

import json
import sqlite3
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, RandomizedSearchCV, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from . import config as C

warnings.filterwarnings("ignore")

NUM = ["exp_overall_years", "exp_field_years", "age_mid", "is_data_role"]
CAT = ["education_std", "industry_std", "job_family", "seniority", "state_std"]
TEXT = "job_title_norm"
FEATURES = NUM + CAT + [TEXT]
AUDIT_COLS = ["gender_std", "exp_overall_band"]


# ----------------------------------------------------------------------------------------------
# Estimators
# ----------------------------------------------------------------------------------------------
class GroupMedianBaseline(BaseEstimator, RegressorMixin):
    """Naive benchmark: median log-salary of the respondent's job family."""

    def fit(self, X, y):
        tmp = X[["job_family"]].copy()
        tmp["y"] = np.asarray(y)
        self.table_ = tmp.groupby("job_family")["y"].median()
        self.global_ = float(np.median(y))
        return self

    def predict(self, X):
        return X["job_family"].map(self.table_).fillna(self.global_).to_numpy()


class RidgeStructured(BaseEstimator, RegressorMixin):
    """Ridge on numeric + one-hot categorical features only."""

    def __init__(self, alpha: float = 3.0):
        self.alpha = alpha

    def fit(self, X, y):
        self.pipe_ = Pipeline([
            ("p", ColumnTransformer([
                ("n", StandardScaler(), NUM),
                ("c", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CAT)])),
            ("m", Ridge(alpha=self.alpha))]).fit(X, y)
        return self

    def predict(self, X):
        return self.pipe_.predict(X)


class RidgeText(BaseEstimator, RegressorMixin):
    """Ridge on structured features + TF-IDF (1-2 grams) of the normalised job title."""

    def __init__(self, alpha: float = 3.0):
        self.alpha = alpha

    def fit(self, X, y):
        self.pipe_ = Pipeline([
            ("p", ColumnTransformer([
                ("n", StandardScaler(), NUM),
                ("c", OneHotEncoder(handle_unknown="ignore", min_frequency=20), CAT),
                ("t", TfidfVectorizer(ngram_range=(1, 2), min_df=8, sublinear_tf=True), TEXT)])),
            ("m", Ridge(alpha=self.alpha))]).fit(X, y)
        return self

    def predict(self, X):
        return self.pipe_.predict(X)


class HGBText(BaseEstimator, RegressorMixin):
    """Gradient boosting with native categoricals + binary job-title token flags."""

    def __init__(self, learning_rate=0.05, max_iter=600, max_leaf_nodes=24, min_samples_leaf=30,
                 l2_regularization=1.0, loss="squared_error", quantile=None, max_tokens=200, random_state=C.RANDOM_STATE):
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.max_leaf_nodes = max_leaf_nodes
        self.min_samples_leaf = min_samples_leaf
        self.l2_regularization = l2_regularization
        self.loss = loss
        self.quantile = quantile
        self.max_tokens = max_tokens
        self.random_state = random_state

    def fit(self, X, y):
        self.pre_ = ColumnTransformer([
            ("n", "passthrough", NUM),
            ("c", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CAT),
            ("t", CountVectorizer(min_df=15, max_features=self.max_tokens, binary=True), TEXT)],
            sparse_threshold=0)
        Z = self.pre_.fit_transform(X)
        mask = [False] * len(NUM) + [True] * len(CAT) + [False] * (Z.shape[1] - len(NUM) - len(CAT))
        self.model_ = HistGradientBoostingRegressor(
            loss=self.loss, quantile=self.quantile, learning_rate=self.learning_rate,
            max_iter=self.max_iter, max_leaf_nodes=self.max_leaf_nodes,
            min_samples_leaf=self.min_samples_leaf, l2_regularization=self.l2_regularization,
            categorical_features=mask, early_stopping=True, random_state=self.random_state).fit(Z, y)
        return self

    def predict(self, X):
        return self.model_.predict(self.pre_.transform(X))


class BlendRegressor(BaseEstimator, RegressorMixin):
    """Weighted blend of RidgeText and HGBText (weights chosen on out-of-fold predictions)."""

    def __init__(self, w_ridge: float = 0.5, hgb_params: dict | None = None):
        self.w_ridge = w_ridge
        self.hgb_params = hgb_params

    def fit(self, X, y):
        self.ridge_ = RidgeText().fit(X, y)
        self.hgb_ = HGBText(**(self.hgb_params or {})).fit(X, y)
        return self

    def predict(self, X):
        return self.w_ridge * self.ridge_.predict(X) + (1 - self.w_ridge) * self.hgb_.predict(X)


# ----------------------------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------------------------
def regression_metrics(y_log: np.ndarray, pred_log: np.ndarray) -> dict:
    y, p = np.exp(y_log), np.exp(pred_log)
    ape = np.abs(p - y) / y
    return {
        "r2_log": float(r2_score(y_log, pred_log)),
        "rmse_log": float(np.sqrt(np.mean((y_log - pred_log) ** 2))),
        "mae_usd": float(mean_absolute_error(y, p)),
        "median_ape_pct": float(100 * np.median(ape)),
        "within_20pct": float(100 * np.mean(ape <= 0.20)),
        "within_30pct": float(100 * np.mean(ape <= 0.30)),
    }


# ----------------------------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------------------------
def load_model_frame(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM vw_analysis WHERE country_std = 'United States'", con)
    df["is_data_role"] = df["is_data_role"].astype(int)
    return df.reset_index(drop=True)


def conformal_interval(X_tr, y_tr, X_te, alpha: float = 0.20):
    """CQR: quantile models on 80% of train, conformity scores on the other 20%."""
    X_fit, X_cal, y_fit, y_cal = train_test_split(X_tr, y_tr, test_size=0.2, random_state=C.RANDOM_STATE)
    lo = HGBText(loss="quantile", quantile=alpha / 2).fit(X_fit, y_fit)
    hi = HGBText(loss="quantile", quantile=1 - alpha / 2).fit(X_fit, y_fit)
    scores = np.maximum(lo.predict(X_cal) - y_cal, y_cal - hi.predict(X_cal))
    n = len(scores)
    q = np.quantile(scores, min(1.0, np.ceil((n + 1) * (1 - alpha)) / n))
    raw_lo, raw_hi = lo.predict(X_te), hi.predict(X_te)
    return raw_lo - q, raw_hi + q, raw_lo, raw_hi, float(q)


def run_modeling(con: sqlite3.Connection, save_model: bool = True) -> dict:
    df = load_model_frame(con)
    X, y = df[FEATURES + AUDIT_COLS], np.log(df["salary_usd"].to_numpy())
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.20, random_state=C.RANDOM_STATE)
    kf = KFold(5, shuffle=True, random_state=C.RANDOM_STATE)
    out: dict = {"n_total": int(len(df)), "n_train": int(len(X_tr)), "n_test": int(len(X_te))}

    # 1) small randomised search for the boosting component (3-fold, train only)
    search = RandomizedSearchCV(
        HGBText(max_iter=400), n_iter=10, cv=3, scoring="r2", random_state=C.RANDOM_STATE, n_jobs=1,
        param_distributions={"learning_rate": [0.03, 0.05, 0.08], "max_leaf_nodes": [15, 24, 31, 48],
                             "min_samples_leaf": [20, 30, 60, 100], "l2_regularization": [0.0, 1.0, 5.0],
                             "max_tokens": [100, 200, 300]}).fit(X_tr[FEATURES], y_tr)
    best_hgb = {k: (v.item() if hasattr(v, "item") else v) for k, v in search.best_params_.items()}
    out["hgb_best_params"], out["hgb_search_cv_r2"] = best_hgb, float(search.best_score_)

    # 2) cross-validated comparison (OOF predictions on train only)
    candidates = {
        "Baseline: median by job family": GroupMedianBaseline(),
        "Ridge (structured features)": RidgeStructured(),
        "Ridge + job-title TF-IDF": RidgeText(),
        "Gradient boosting + title tokens": HGBText(**best_hgb),
    }
    oof: dict[str, np.ndarray] = {}
    for name, est in candidates.items():
        oof[name] = cross_val_predict(est, X_tr[FEATURES], y_tr, cv=kf)
    # blend weight picked on OOF predictions
    grid = np.linspace(0, 1, 11)
    w = float(grid[np.argmax([r2_score(y_tr, g * oof["Ridge + job-title TF-IDF"] +
                                       (1 - g) * oof["Gradient boosting + title tokens"]) for g in grid])])
    oof["Blend (selected)"] = w * oof["Ridge + job-title TF-IDF"] + (1 - w) * oof["Gradient boosting + title tokens"]
    out["blend_weight_ridge"] = w
    out["cv"] = {k: regression_metrics(y_tr, v) for k, v in oof.items()}

    # 3) final fit + one-shot holdout evaluation
    final = BlendRegressor(w_ridge=w, hgb_params=best_hgb).fit(X_tr[FEATURES], y_tr)
    pred_te = final.predict(X_te[FEATURES])
    base = GroupMedianBaseline().fit(X_tr[FEATURES], y_tr).predict(X_te[FEATURES])
    out["holdout"] = regression_metrics(y_te, pred_te)
    out["holdout_baseline"] = regression_metrics(y_te, base)

    # 4) prediction intervals (80%) with conformal calibration
    lo_c, hi_c, lo_raw, hi_raw, qhat = conformal_interval(X_tr[FEATURES], y_tr, X_te[FEATURES], alpha=0.20)
    out["interval"] = {
        "nominal_coverage_pct": 80.0,
        "raw_quantile_coverage_pct": float(100 * np.mean((y_te >= lo_raw) & (y_te <= hi_raw))),
        "conformal_coverage_pct": float(100 * np.mean((y_te >= lo_c) & (y_te <= hi_c))),
        "conformal_median_width_usd": float(np.median(np.exp(hi_c) - np.exp(lo_c))),
        "conformal_qhat_log": qhat,
    }

    # 5) permutation importance on raw feature columns (test set)
    pi = permutation_importance(final, X_te[FEATURES], y_te, n_repeats=8, random_state=C.RANDOM_STATE,
                                scoring="r2", n_jobs=1)
    imp = (pd.DataFrame({"feature": FEATURES, "r2_drop": pi.importances_mean, "std": pi.importances_std})
           .sort_values("r2_drop", ascending=False).reset_index(drop=True))
    out["importance"] = imp.to_dict("records")

    # 6) residual audit on the test set (gender is NOT a model input)
    audit = X_te[AUDIT_COLS].copy()
    audit["y_log"], audit["pred_log"] = y_te, pred_te
    audit["resid_log"] = audit["y_log"] - audit["pred_log"]
    audit["ape"] = np.abs(np.exp(audit["pred_log"]) - np.exp(audit["y_log"])) / np.exp(audit["y_log"])
    audit["lo"], audit["hi"] = np.exp(lo_c), np.exp(hi_c)
    audit["y"], audit["pred"] = np.exp(y_te), np.exp(pred_te)
    audit["job_family"] = X_te["job_family"].values
    rng = np.random.default_rng(C.RANDOM_STATE)
    gender_rows = []
    for g in ["Woman", "Man"]:
        r = audit.loc[audit["gender_std"] == g, "resid_log"].to_numpy()
        boots = [rng.choice(r, len(r)).mean() for _ in range(2000)]
        gender_rows.append({"gender": g, "n_test": int(len(r)), "mean_resid_log": float(r.mean()),
                            "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)),
                            "pct_effect": float(100 * (np.exp(r.mean()) - 1))})
    out["gender_residuals"] = gender_rows
    seg = (audit.groupby("exp_overall_band").agg(n=("ape", "size"), median_ape_pct=("ape", lambda s: 100 * s.median()))
           .reset_index())
    out["error_by_experience"] = seg.to_dict("records")
    fam = (audit.groupby("job_family").agg(n=("ape", "size"), median_ape_pct=("ape", lambda s: 100 * s.median()))
           .query("n >= 40").sort_values("median_ape_pct").reset_index())
    out["error_by_family"] = fam.to_dict("records")

    # 7) artefacts
    (C.REPORT_DIR / "tables").mkdir(parents=True, exist_ok=True)
    audit.to_csv(C.REPORT_DIR / "tables" / "model_test_predictions.csv", index=False)
    imp.to_csv(C.REPORT_DIR / "tables" / "model_permutation_importance.csv", index=False)
    pd.DataFrame(out["cv"]).T.round(4).to_csv(C.REPORT_DIR / "tables" / "model_cv_comparison.csv")
    (C.REPORT_DIR / "model_metrics.json").write_text(json.dumps(out, indent=2, default=float))
    if save_model:
        refit = BlendRegressor(w_ridge=w, hgb_params=best_hgb).fit(X[FEATURES], y)
        lo_m = HGBText(loss="quantile", quantile=0.10).fit(X[FEATURES], y)
        hi_m = HGBText(loss="quantile", quantile=0.90).fit(X[FEATURES], y)
        (C.ROOT / "models").mkdir(exist_ok=True)
        joblib.dump({"point": refit, "q10": lo_m, "q90": hi_m, "qhat_log": qhat, "features": FEATURES},
                    C.ROOT / "models" / "salary_model.joblib", compress=3)
    return out
