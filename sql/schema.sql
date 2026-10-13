-- Warehouse schema (SQLite). Raw layer is immutable; clean layer is a star-ish model.
PRAGMA foreign_keys = ON;

-- ---------- RAW LAYER (exactly as received) ----------
DROP TABLE IF EXISTS raw_survey;
CREATE TABLE raw_survey (
    row_id                                   INTEGER PRIMARY KEY,
    timestamp                                TEXT,
    how_old_are_you                          TEXT,
    industry                                 TEXT,
    job_title                                TEXT,
    additional_context_on_job_title          TEXT,
    annual_salary                            REAL,
    other_monetary_comp                      REAL,
    currency                                 TEXT,
    currency_other                           TEXT,
    additional_context_on_income             TEXT,
    country                                  TEXT,
    state                                    TEXT,
    city                                     TEXT,
    overall_years_of_professional_experience TEXT,
    years_of_experience_in_field             TEXT,
    highest_level_of_education_completed     TEXT,
    gender                                   TEXT,
    race                                     TEXT
);

-- ---------- DIMENSIONS ----------
DROP TABLE IF EXISTS dim_country;
CREATE TABLE dim_country (
    country_id  INTEGER PRIMARY KEY,
    country_std TEXT NOT NULL UNIQUE
);

DROP TABLE IF EXISTS dim_industry;
CREATE TABLE dim_industry (
    industry_id  INTEGER PRIMARY KEY,
    industry_std TEXT NOT NULL UNIQUE
);

DROP TABLE IF EXISTS dim_job_family;
CREATE TABLE dim_job_family (
    job_family_id INTEGER PRIMARY KEY,
    job_family    TEXT NOT NULL UNIQUE
);

DROP TABLE IF EXISTS dim_currency;
CREATE TABLE dim_currency (
    currency_code TEXT PRIMARY KEY,
    usd_per_unit  REAL,            -- APPROXIMATE, mid-May-2021 snapshot (see config.py)
    fx_note       TEXT
);

-- ---------- AUDIT / MAPPING TABLES ----------
DROP TABLE IF EXISTS map_country_raw;
CREATE TABLE map_country_raw (
    raw_value   TEXT,
    country_std TEXT NOT NULL,
    method      TEXT NOT NULL,
    n_rows      INTEGER NOT NULL
);

DROP TABLE IF EXISTS map_industry_raw;
CREATE TABLE map_industry_raw (
    raw_value    TEXT,
    industry_std TEXT NOT NULL,
    method       TEXT NOT NULL,
    n_rows       INTEGER NOT NULL
);

DROP TABLE IF EXISTS dq_issue_log;
CREATE TABLE dq_issue_log (
    row_id   INTEGER NOT NULL,
    rule_id  TEXT NOT NULL,
    severity TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT,
    FOREIGN KEY (row_id) REFERENCES raw_survey(row_id)
);

DROP TABLE IF EXISTS dq_summary;
CREATE TABLE dq_summary (
    rule_id     TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    severity    TEXT NOT NULL,
    action      TEXT NOT NULL,
    n_rows      INTEGER NOT NULL,
    pct_rows    REAL NOT NULL
);

-- ---------- FACT ----------
DROP TABLE IF EXISTS fact_response;
CREATE TABLE fact_response (
    row_id              INTEGER PRIMARY KEY,
    submitted_at        TEXT NOT NULL,
    age_band            TEXT,
    age_mid             REAL,
    education_std       TEXT NOT NULL,
    education_rank      REAL,
    gender_std          TEXT NOT NULL,
    country_id          INTEGER NOT NULL,
    country_method      TEXT NOT NULL,
    state_std           TEXT NOT NULL,
    city_norm           TEXT,
    industry_id         INTEGER NOT NULL,
    industry_method     TEXT NOT NULL,
    job_title_norm      TEXT,
    job_family_id       INTEGER NOT NULL,
    seniority           TEXT NOT NULL,
    is_data_role        INTEGER NOT NULL CHECK (is_data_role IN (0,1)),
    exp_overall_band    TEXT,
    exp_overall_ord     INTEGER,
    exp_overall_years   REAL,
    exp_field_band      TEXT,
    exp_field_ord       INTEGER,
    exp_field_years     REAL,
    currency_code       TEXT NOT NULL,
    currency_method     TEXT NOT NULL,
    salary_local        REAL,
    other_comp_local    REAL,
    salary_usd          REAL,
    other_comp_usd      REAL,
    total_comp_usd      REAL,
    other_comp_missing  INTEGER NOT NULL CHECK (other_comp_missing IN (0,1)),
    is_duplicate        INTEGER NOT NULL CHECK (is_duplicate IN (0,1)),
    is_salary_valid     INTEGER NOT NULL CHECK (is_salary_valid IN (0,1)),
    salary_invalid_reason TEXT,
    field_gt_overall    INTEGER NOT NULL CHECK (field_gt_overall IN (0,1)),
    age_exp_impossible  INTEGER NOT NULL CHECK (age_exp_impossible IN (0,1)),
    is_analysis_ready   INTEGER NOT NULL CHECK (is_analysis_ready IN (0,1)),
    FOREIGN KEY (row_id)        REFERENCES raw_survey(row_id),
    FOREIGN KEY (country_id)    REFERENCES dim_country(country_id),
    FOREIGN KEY (industry_id)   REFERENCES dim_industry(industry_id),
    FOREIGN KEY (job_family_id) REFERENCES dim_job_family(job_family_id)
);

-- multi-select 'race' answer exploded to one row per option (many-to-many)
DROP TABLE IF EXISTS bridge_response_race;
CREATE TABLE bridge_response_race (
    row_id      INTEGER NOT NULL,
    race_option TEXT NOT NULL,
    PRIMARY KEY (row_id, race_option),
    FOREIGN KEY (row_id) REFERENCES fact_response(row_id)
);

CREATE INDEX ix_fact_ready    ON fact_response(is_analysis_ready, country_id);
CREATE INDEX ix_fact_industry ON fact_response(industry_id);
CREATE INDEX ix_fact_family   ON fact_response(job_family_id);
CREATE INDEX ix_issue_rule    ON dq_issue_log(rule_id);

-- ---------- ANALYTICS VIEW: only trustworthy rows, dimensions joined ----------
DROP VIEW IF EXISTS vw_analysis;
CREATE VIEW vw_analysis AS
SELECT f.*, c.country_std, i.industry_std, j.job_family
FROM fact_response f
JOIN dim_country    c ON c.country_id    = f.country_id
JOIN dim_industry   i ON i.industry_id   = f.industry_id
JOIN dim_job_family j ON j.job_family_id = f.job_family_id
WHERE f.is_analysis_ready = 1;
