-- A01: Salary distribution by total professional experience (US, analysis-ready rows).
-- SQLite has no PERCENTILE function -> median/quartiles via ROW_NUMBER() / COUNT() window functions.
WITH base AS (
    SELECT exp_overall_ord AS ord, exp_overall_band AS band, salary_usd AS v
    FROM vw_analysis
    WHERE country_std = 'United States'
), ranked AS (
    SELECT ord, band, v,
           ROW_NUMBER() OVER (PARTITION BY ord ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY ord)            AS n
    FROM base
)
SELECT band                                                         AS experience_band,
       n                                                            AS respondents,
       ROUND(AVG(v))                                                AS mean_usd,
       ROUND(AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END)) AS median_usd,
       MIN(CASE WHEN rn >= 0.25 * n THEN v END)                     AS p25_usd,
       MIN(CASE WHEN rn >= 0.75 * n THEN v END)                     AS p75_usd
FROM ranked
GROUP BY ord, band
ORDER BY ord;
