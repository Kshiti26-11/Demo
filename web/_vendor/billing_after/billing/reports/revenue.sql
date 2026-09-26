SELECT date(created_at) AS day, SUM(total_price) AS revenue FROM orders WHERE status IN ('PAID', 'SHIPPED') GROUP BY day ORDER BY day
