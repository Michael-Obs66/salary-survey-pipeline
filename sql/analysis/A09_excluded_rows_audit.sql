-- A09: Why rows were excluded - counts and the most extreme examples (raw value vs interpretation).
SELECT COALESCE(salary_invalid_reason, 'valid salary but excluded for another rule') AS reason,
       COUNT(*) AS rows_excluded
FROM fact_response
WHERE is_analysis_ready = 0 AND is_duplicate = 0
GROUP BY 1 ORDER BY rows_excluded DESC;
