-- A04: State-level median salary (US, n >= 150) vs national median, with RANK() and window AVG baseline.
WITH base AS (
    SELECT state_std AS grp, salary_usd AS v FROM vw_analysis
    WHERE country_std = 'United States' AND state_std NOT IN ('Unknown', 'Multiple states')
), ranked AS (
    SELECT grp, v,
           ROW_NUMBER() OVER (PARTITION BY grp ORDER BY v) AS rn,
           COUNT(*)     OVER (PARTITION BY grp)            AS n
    FROM base
), med AS (
    SELECT grp, MAX(n) AS respondents,
           AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN v END) AS median_usd
    FROM ranked GROUP BY grp HAVING MAX(n) >= 150
)
SELECT RANK() OVER (ORDER BY median_usd DESC) AS rank,
       grp AS state, respondents, ROUND(median_usd) AS median_usd,
       ROUND(median_usd - AVG(median_usd) OVER ()) AS diff_vs_avg_of_states_usd
FROM med ORDER BY rank LIMIT 15;
