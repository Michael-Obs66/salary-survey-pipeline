-- A03: Do data roles earn a premium? Median base salary by experience band, pivoted by role group (US).
-- Conditional aggregation after a ranking CTE; groups with < 15 respondents in a cell are suppressed.
WITH base AS (
    SELECT exp_overall_ord AS ord, exp_overall_band AS band, salary_usd AS v,
           CASE WHEN job_family = 'Data & Analytics'     THEN 'data'
                WHEN job_family = 'Software Engineering' THEN 'software'
                WHEN job_family = 'IT & Systems'         THEN 'it'
                ELSE 'all_other' END AS grp
    FROM vw_analysis WHERE country_std = 'United States'
), ranked AS (
    SELECT ord, band, grp, v,
           ROW_NUMBER() OVER (PARTITION BY ord, grp ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY ord, grp)            AS n
    FROM base
), med AS (
    SELECT ord, band, grp, MAX(n) AS n,
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS m
    FROM ranked GROUP BY ord, band, grp
)
SELECT band AS experience_band,
       MAX(CASE WHEN grp='data'      AND n >= 15 THEN ROUND(m) END) AS data_median_usd,
       MAX(CASE WHEN grp='data'      THEN n END)                    AS data_n,
       MAX(CASE WHEN grp='software'  AND n >= 15 THEN ROUND(m) END) AS software_median_usd,
       MAX(CASE WHEN grp='it'        AND n >= 15 THEN ROUND(m) END) AS it_median_usd,
       MAX(CASE WHEN grp='all_other' AND n >= 15 THEN ROUND(m) END) AS all_other_median_usd,
       ROUND(MAX(CASE WHEN grp='data' AND n >= 15 THEN m END) /
             MAX(CASE WHEN grp='all_other' THEN m END), 2)          AS data_vs_all_other_ratio
FROM med GROUP BY ord, band ORDER BY ord;
