-- A07: Raw (unadjusted) median salary by gender within experience band, US, cells n >= 30.
-- Observational + self-selected survey: NOT a causal estimate of discrimination.
WITH base AS (
    SELECT exp_overall_ord AS ord, exp_overall_band AS band, gender_std AS g, salary_usd AS v
    FROM vw_analysis WHERE country_std = 'United States' AND gender_std IN ('Woman', 'Man')
), ranked AS (
    SELECT ord, band, g, v,
           ROW_NUMBER() OVER (PARTITION BY ord, g ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY ord, g)            AS n
    FROM base
), med AS (
    SELECT ord, band, g, MAX(n) AS n,
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS m
    FROM ranked GROUP BY ord, band, g HAVING MAX(n) >= 30
)
SELECT w.band AS experience_band, w.n AS women_n, m.n AS men_n,
       ROUND(w.m) AS women_median_usd, ROUND(m.m) AS men_median_usd,
       ROUND(w.m / m.m, 3) AS women_to_men_ratio
FROM med w JOIN med m ON w.ord = m.ord AND w.g = 'Woman' AND m.g = 'Man'
ORDER BY w.ord;
