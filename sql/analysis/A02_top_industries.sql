-- A02: Highest-paying industries (US, n >= 100) by MEDIAN total compensation, ranked, with ratio to US median.
WITH base AS (
    SELECT industry_std AS grp, total_comp_usd AS v FROM vw_analysis
    WHERE country_std = 'United States' AND industry_std <> 'Other / Unclassified'
), ranked AS (
    SELECT grp, v,
           ROW_NUMBER() OVER (PARTITION BY grp ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY grp)            AS n
    FROM base
), med AS (
    SELECT grp, MAX(n) AS respondents,
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS median_total_comp
    FROM ranked GROUP BY grp HAVING MAX(n) >= 100
), us_median AS (
    SELECT AVG(v) AS m FROM (
        SELECT v, ROW_NUMBER() OVER (ORDER BY v) rn, COUNT(*) OVER () n FROM base
    ) WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
)
SELECT RANK() OVER (ORDER BY median_total_comp DESC)  AS rank,
       grp                                            AS industry,
       respondents,
       ROUND(median_total_comp)                       AS median_total_comp_usd,
       ROUND(median_total_comp / (SELECT m FROM us_median), 2) AS ratio_to_us_median
FROM med
ORDER BY rank
LIMIT 15;
