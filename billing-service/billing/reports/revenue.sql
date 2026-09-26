-- v2 schema: total_minor column (integer minor units).
-- See revenue.py for tolerant-reader column detection that selects this or the v1 variant.
SELECT date(created_at) AS day, SUM(total_minor) AS revenue
FROM orders
WHERE status IN ('PAID', 'SHIPPED')
GROUP BY day
ORDER BY day
