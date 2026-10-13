-- A06: Cross-country median salary in USD-equivalent (n >= 100). DESCRIPTIVE ONLY:
-- FX is an approximate May-2021 snapshot and no purchasing-power adjustment is applied.
WITH base AS (
    SELECT country_std AS grp, salary_usd AS v FROM vw_analysis
), ranked AS (
    SELECT grp, v,
           ROW_NUMBER() OVER (PARTITION BY grp ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY grp)            AS n
    FROM base
)
SELECT grp AS country, MAX(n) AS respondents,
       ROUND(AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END)) AS median_usd_equiv
FROM ranked GROUP BY grp HAVING MAX(n) >= 100
ORDER BY median_usd_equiv DESC;
