-- A10: How each raw country spelling was resolved (distinct spellings and rows covered per method).
SELECT method AS country_resolution_method,
       COUNT(*)      AS distinct_raw_spellings,
       SUM(n_rows)   AS rows_covered,
       ROUND(100.0 * SUM(n_rows) / (SELECT SUM(n_rows) FROM map_country_raw), 2) AS pct_rows
FROM map_country_raw GROUP BY method ORDER BY rows_covered DESC;
