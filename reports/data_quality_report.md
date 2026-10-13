# Data Quality Report

Gates: **18/18 PASS**

## Validation gates (post-load, run against the SQLite warehouse)

| ID | Check | Observed | Expected | Status |
|---|---|---|---|---|
| Q01 | Row reconciliation: fact_response == raw_survey | 26232.0 | == 26232 | PASS |
| Q02 | No orphan foreign keys | 0.0 | == 0 | PASS |
| Q03 | Primary key unique in fact_response | 0.0 | == 0 | PASS |
| Q04 | Every country_std in dim_country is unique | 0.0 | == 0 | PASS |
| Q05 | Ready rows have salary_usd within [floor, cap] | 0.0 | == 0 | PASS |
| Q06 | Ready rows are never duplicates / invalid / impossible-age | 0.0 | == 0 | PASS |
| Q07 | Ready rows have a resolved currency | 0.0 | == 0 | PASS |
| Q08 | Ready rows: years in field <= total years (after repair) | 0.0 | == 0 | PASS |
| Q09 | Ready rows: total_comp_usd >= salary_usd | 0.0 | == 0 | PASS |
| Q10 | Dropped duplicates all excluded from analysis | 0.0 | == 0 | PASS |
| Q11 | Seniority only takes allowed values | 0.0 | == 0 | PASS |
| Q12 | Survey timestamps inside the collection window (2021-04-27..2021-05-17) | 0.0 | == 0 | PASS |
| Q13 | No placeholder state for US ready rows other than Unknown/Multiple | 0.0 | == 0 | PASS |
| Q14 | Multi-select race options parsed with no comma fragments | 0.0 | == 0 | PASS |
| Q15 | Country unresolved rows <= 0.5% | 0.114 | <= 0.5 | PASS |
| Q16 | Industry unclassified rows <= 2% | 0.991 | <= 2.0 | PASS |
| Q17 | Job family 'Other' <= 6% | 4.19 | <= 6.0 | PASS |
| Q18 | At least 97% of rows survive cleaning (not over-filtering) | 98.61 | >= 97.0 | PASS |

## Cleansing rules fired (audit catalogue)

| Rule | Description | Severity | Action | Rows | % |
|---|---|---|---|---:|---:|
| R00 | Unparseable timestamp | high | flag | 0 | 0.0 |
| R01 | Re-submitted identical response (<=48h after first) | high | drop_from_analysis | 148 | 0.56 |
| R02 | Country repaired via fuzzy/substring/manual rule | medium | fix | 150 | 0.57 |
| R03 | Country unresolved | high | drop_from_analysis | 30 | 0.11 |
| R04 | US respondent lists several states -> 'Multiple states' | low | fix | 97 | 0.37 |
| R05 | US respondent without state -> 'Unknown' | low | fix | 172 | 0.66 |
| R06 | Currency recovered from 'Other' free text or AUD/NZD ambiguity | medium | fix | 578 | 2.2 |
| R07 | Currency unresolved ('Other' without usable detail) | high | drop_from_analysis | 24 | 0.09 |
| R08a | Salary is zero or negative | high | drop_from_analysis | 10 | 0.04 |
| R08b | Salary 1-999 in a major currency: thousands or hourly? (ambiguous) | high | drop_from_analysis | 75 | 0.29 |
| R08c | Salary below USD 10,000 | high | drop_from_analysis | 43 | 0.16 |
| R08d | Salary above USD 1,000,000 | high | drop_from_analysis | 15 | 0.06 |
| R09 | Other compensation blank -> treated as 0 | low | impute | 6,785 | 25.87 |
| R10 | Other compensation > 5x salary -> nulled | medium | fix | 30 | 0.11 |
| R11 | Years in field > total years -> capped at total years | medium | fix | 233 | 0.89 |
| R12 | Age band incompatible with experience band | high | drop_from_analysis | 20 | 0.08 |
| R13 | Free-text industry mapped to a standard category | medium | fix | 1,758 | 6.7 |
| R14 | Industry unclassified/missing | low | flag | 260 | 0.99 |
| R15 | Job title not mapped to a job family | low | flag | 1,099 | 4.19 |
| R16 | Currency differs from country's domestic currency (expat or mislabel) | low | flag | 89 | 0.34 |
| R17 | Education missing -> 'Unknown' | low | fix | 196 | 0.75 |
| R18 | Gender missing -> 'Unknown' | low | fix | 148 | 0.56 |
| R99 | Row excluded from analysis (any blocking rule) | info | summary | 364 | 1.39 |
