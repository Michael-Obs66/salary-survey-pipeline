"""Static figures for the case study (palette + mark rules from the dataviz skill's reference instance)."""
from __future__ import annotations

import json
import sqlite3

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, MUTED = "#2a78d6", "#eb6834", "#b9b8b2"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "font.size": 10, "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def _save(fig, name):
    C.FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.FIG_DIR / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _usd(x, _=None):
    return f"${x/1000:,.0f}k" if x < 1e6 else f"${x/1e6:,.1f}M"


def fig_cleaning_impact(con, ba: dict):
    raw = pd.read_sql_query("SELECT annual_salary FROM raw_survey", con)["annual_salary"]
    fact = pd.read_sql_query("SELECT salary_usd FROM fact_response WHERE is_analysis_ready=1", con)["salary_usd"]
    fig, ax = plt.subplots(1, 3, figsize=(14.5, 3.9), gridspec_kw={"width_ratios": [1, 1.35, 1]})

    # (a) distinct spellings before/after
    items = [("Country", ba["country_distinct_raw"], ba["country_distinct_clean"]),
             ("Industry", ba["industry_distinct_raw"], ba["industry_distinct_clean"])]
    a = ax[0]
    y = np.arange(len(items))[::-1]
    a.barh(y + 0.19, [i[1] for i in items], height=0.34, color=MUTED, label="Raw")
    a.barh(y - 0.19, [i[2] for i in items], height=0.34, color=BLUE, label="Clean")
    for yi, (_, r, c) in zip(y, items):
        a.text(r + 15, yi + 0.19, f"{r:,}", va="center", fontsize=9, color=INK2)
        a.text(c + 15, yi - 0.19, f"{c:,}", va="center", fontsize=9, color=INK)
    a.set_yticks(y, [i[0] for i in items]); a.set_xlim(0, 1250); a.grid(axis="y", visible=False)
    a.set_title("Distinct spellings per field"); a.legend(frameon=False, loc="center right")

    # (b) salary distribution raw vs clean
    b = ax[1]
    bins = np.linspace(0, 9, 55)
    b.hist(np.log10(raw[raw > 0]), bins=bins, color=MUTED, label="Raw (mixed currencies)")
    b.hist(np.log10(fact), bins=bins, color=BLUE, alpha=0.9, label="Clean (USD, valid)")
    b.set_xticks([3, 5, 7, 9], ["$1k", "$100k", "$10M", "$1B"]); b.set_xlim(2, 9.3); b.set_ylim(0, 9500)
    b.set_title("Salary on a log scale"); b.set_ylabel("Respondents"); b.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 1.0))
    b.annotate("max raw value:\n870,000,000", xy=(8.94, 4), xytext=(6.6, 3200), fontsize=8.5, color=INK2,
               arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))

    # (c) row funnel
    f = pd.read_sql_query("""SELECT COUNT(*) n_raw,
        SUM(CASE WHEN is_duplicate=0 THEN 1 ELSE 0 END) n_nodup,
        SUM(CASE WHEN is_duplicate=0 AND is_salary_valid=1 THEN 1 ELSE 0 END) n_valid,
        SUM(is_analysis_ready) n_ready FROM fact_response""", con).iloc[0]
    steps = [("Raw rows", f.n_raw), ("No duplicates", f.n_nodup), ("Valid salary", f.n_valid), ("Analysis-ready", f.n_ready)]
    c = ax[2]
    yy = np.arange(len(steps))[::-1]
    c.barh(yy, [s[1] for s in steps], color=[MUTED, MUTED, MUTED, BLUE], height=0.6)
    for yi, (_, n) in zip(yy, steps):
        c.text(n + 200, yi, f"{int(n):,}", va="center", fontsize=9, color=INK)
    c.set_yticks(yy, [s[0] for s in steps]); c.set_xlim(24000, 27400)
    c.set_title("Row funnel (truncated axis)"); c.grid(axis="y", visible=False)
    c.set_xticks([24000, 25000, 26000, 27000], ["24k", "25k", "26k", "27k"])
    fig.tight_layout()
    _save(fig, "fig1_cleaning_impact.png")


def fig_salary_experience(a01: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    x = np.arange(len(a01))
    ax.fill_between(x, a01["p25_usd"], a01["p75_usd"], color=BLUE, alpha=0.16, lw=0, label="Middle 50% (p25-p75)")
    ax.plot(x, a01["median_usd"], color=BLUE, lw=2, marker="o", ms=6, mec=SURFACE, mew=1.5, label="Median")
    for xi, r in zip(x, a01.itertuples()):
        ax.text(xi, r.median_usd + 4500, _usd(r.median_usd), ha="center", fontsize=8.5, color=INK)
        ax.text(xi, 5000, f"n={r.respondents:,}", ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(x, [b.replace(" years", "").replace("1 year or less", "\u22641") for b in a01["experience_band"]])
    ax.set_xlabel("Total professional experience (years)"); ax.set_ylim(0, 150000)
    ax.yaxis.set_major_formatter(_usd); ax.set_title("US base salary by experience: gains flatten after ~20 years")
    ax.legend(frameon=False, loc="upper left")
    _save(fig, "fig2_salary_by_experience.png")


def fig_industries(a02: pd.DataFrame):
    d = a02.sort_values("median_total_comp_usd")
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    colors = [BLUE if i in ("Computing or Tech",) else MUTED for i in d["industry"]]
    ax.barh(d["industry"], d["median_total_comp_usd"], color=colors, height=0.66)
    for y, r in enumerate(d.itertuples()):
        ax.text(r.median_total_comp_usd + 1800, y, f"{_usd(r.median_total_comp_usd)}  (n={r.respondents:,})",
                va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, 175000); ax.xaxis.set_major_formatter(_usd); ax.grid(axis="y", visible=False)
    ax.set_title("Median total compensation, top US industries (n >= 100)")
    _save(fig, "fig3_top_industries.png")


def fig_model(m: dict):
    pred = pd.read_csv(C.REPORT_DIR / "tables" / "model_test_predictions.csv")
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6), gridspec_kw={"width_ratios": [1.05, 1]})
    a = ax[0]
    hb = a.hexbin(pred["pred"], pred["y"], gridsize=48, xscale="log", yscale="log", bins="log",
                  cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#e8f0fb", "#2a78d6", "#0f3d7a"]),
                  mincnt=1, linewidths=0.1, extent=(np.log10(2.5e4), np.log10(6e5), np.log10(1e4), np.log10(1e6)))
    lim = [1.5e4, 8e5]
    a.plot(lim, lim, color=INK, lw=1.2, label="Perfect prediction")
    a.plot(lim, [v * 1.2 for v in lim], color=INK2, lw=0.9, ls="--"); a.plot(lim, [v / 1.2 for v in lim], color=INK2, lw=0.9, ls="--", label="+/-20%")
    a.set_xlim(2.5e4, 6e5); a.set_ylim(1e4, 1e6)
    for axis in (a.xaxis, a.yaxis):
        axis.set_major_formatter(_usd)
    a.set_xticks([3e4, 5e4, 1e5, 2e5, 4e5]); a.set_yticks([2e4, 5e4, 1e5, 2e5, 5e5])
    a.minorticks_off(); a.set_xlabel("Predicted salary"); a.set_ylabel("Actual salary")
    a.set_title(f"Holdout: R²={m['holdout']['r2_log']:.2f}, median error {m['holdout']['median_ape_pct']:.0f}%")
    a.legend(frameon=False, loc="upper left"); a.grid(False)

    b = ax[1]
    names = list(m["cv"].keys())
    short = ["Median by\njob family", "Ridge\n(structured)", "Ridge +\ntitle TF-IDF", "Boosting +\ntitle tokens", "Blend\n(selected)"]
    vals = [m["cv"][n]["r2_log"] for n in names]
    cols = [MUTED] * 4 + [BLUE]
    b.bar(range(5), vals, color=cols, width=0.62)
    for i, v in enumerate(vals):
        b.text(i, v - 0.045 if v > 0.3 else v + 0.012, f"{v:.2f}", ha="center", fontsize=9.5,
               color=SURFACE if i == 4 else INK)
    b.axhline(m["holdout"]["r2_log"], color=ORANGE, lw=1.6)
    b.text(-0.4, m["holdout"]["r2_log"] + 0.02, f"holdout test (touched once): {m['holdout']['r2_log']:.2f}", color=INK, fontsize=8.5)
    b.set_xticks(range(5), short, fontsize=8.5); b.set_ylim(0, 0.75); b.grid(axis="x", visible=False)
    b.set_ylabel("R² on log-salary (5-fold CV)"); b.set_title("Model comparison (train-only cross-validation)")
    fig.tight_layout(); _save(fig, "fig4_model_performance.png")


def fig_importance(m: dict):
    imp = pd.DataFrame(m["importance"])
    imp = imp[imp["feature"] != "is_data_role"].sort_values("r2_drop")
    labels = {"industry_std": "Industry", "job_title_norm": "Job title (text)", "state_std": "US state",
              "seniority": "Seniority level", "exp_field_years": "Years in field", "education_std": "Education",
              "job_family": "Job family", "exp_overall_years": "Total experience", "age_mid": "Age"}
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    ax.barh([labels.get(f, f) for f in imp["feature"]], imp["r2_drop"], xerr=imp["std"], color=BLUE, height=0.62,
            error_kw=dict(ecolor=INK2, lw=0.9, capsize=2))
    ax.set_xlabel("Drop in holdout R² when the feature is shuffled"); ax.grid(axis="y", visible=False)
    ax.set_title("What the model relies on (permutation importance)")
    _save(fig, "fig5_feature_importance.png")


def fig_gender(a07: pd.DataFrame, m: dict):
    fig, ax = plt.subplots(1, 2, figsize=(12, 3.9), gridspec_kw={"width_ratios": [1.5, 1]})
    a = ax[0]
    x = np.arange(len(a07))
    a.bar(x, a07["women_to_men_ratio"], color=ORANGE, width=0.6)
    a.axhline(1.0, color=INK, lw=1)
    for xi, r in zip(x, a07["women_to_men_ratio"]):
        a.text(xi, r + 0.015, f"{r:.2f}", ha="center", fontsize=9)
    a.set_xticks(x, [b.replace(" years", "").replace("1 year or less", "\u22641") for b in a07["experience_band"]])
    a.set_ylim(0, 1.15); a.set_xlabel("Total experience (years)"); a.grid(axis="x", visible=False)
    a.set_title("Raw: women's median salary as a share of men's")
    b = ax[1]
    g = pd.DataFrame(m["gender_residuals"])
    ypos = [1, 0]
    b.errorbar(g["pct_effect"], ypos, xerr=[g["pct_effect"] - 100 * (np.exp(g["ci_low"]) - 1), 100 * (np.exp(g["ci_high"]) - 1) - g["pct_effect"]],
               fmt="o", color=BLUE, ecolor=BLUE, ms=7, mec=SURFACE, mew=1.5, lw=2, capsize=3)
    b.axvline(0, color=INK, lw=1)
    b.set_yticks(ypos, [f"{r.gender} (n={r.n_test:,})" for r in g.itertuples()]); b.set_ylim(-0.6, 1.6)
    b.set_xlabel("Actual vs model-predicted salary (%)"); b.grid(axis="y", visible=False)
    b.set_title("After controls: unexplained gap")
    fig.tight_layout(); _save(fig, "fig6_gender_gap.png")


def make_all(con: sqlite3.Connection, sql_results: dict, model_metrics: dict, before_after: dict):
    fig_cleaning_impact(con, before_after)
    fig_salary_experience(sql_results["A01_salary_by_experience"])
    fig_industries(sql_results["A02_top_industries"])
    fig_model(model_metrics)
    fig_importance(model_metrics)
    fig_gender(sql_results["A07_gender_gap_by_experience"], model_metrics)
