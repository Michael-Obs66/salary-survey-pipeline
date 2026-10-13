-- A05: Education premium AT EQUAL EXPERIENCE. Median salary by education x experience band (US),
-- premium expressed vs the 'College degree' median of the same band (cells with n < 30 suppressed).
WITH base AS (
    SELECT exp_overall_ord AS ord, exp_overall_band AS band, education_std AS edu, salary_usd AS v
    FROM vw_analysis
    WHERE country_std = 'United States' AND education_std <> 'Unknown' AND exp_overall_ord BETWEEN 2 AND 5
), ranked AS (
    SELECT ord, band, edu, v,
           ROW_NUMBER() OVER (PARTITION BY ord, edu ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY ord, edu)            AS n
    FROM base
), med AS (
    SELECT ord, band, edu, MAX(n) AS n,
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS m
    FROM ranked GROUP BY ord, band, edu HAVING MAX(n) >= 30
)
SELECT a.band AS experience_band, a.edu AS education, a.n AS respondents,
       ROUND(a.m) AS median_usd,
       ROUND(a.m / b.m - 1, 3) AS premium_vs_college_degree
FROM med a JOIN med b ON a.ord = b.ord AND b.edu = 'College degree'
ORDER BY a.ord, a.m DESC;
