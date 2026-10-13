-- A08: Median salary growth between consecutive experience bands, using LAG() (US).
WITH base AS (
    SELECT exp_overall_ord AS ord, exp_overall_band AS band, salary_usd AS v
    FROM vw_analysis WHERE country_std = 'United States'
), ranked AS (
    SELECT ord, band, v,
           ROW_NUMBER() OVER (PARTITION BY ord ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY ord)            AS n
    FROM base
), med AS (
    SELECT ord, band, AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS m
    FROM ranked GROUP BY ord, band
)
SELECT band AS experience_band, ROUND(m) AS median_usd,
       ROUND(m - LAG(m) OVER (ORDER BY ord)) AS step_up_usd,
       ROUND(m / LAG(m) OVER (ORDER BY ord) - 1, 3) AS step_up_pct
FROM med ORDER BY ord;
