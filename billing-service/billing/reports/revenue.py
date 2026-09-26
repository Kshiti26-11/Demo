from pathlib import Path

from sqlalchemy import create_engine, inspect, text

# v2 SQL — reads total_minor directly (already in minor units)
_SQL_V2 = (Path(__file__).parent / "revenue.sql").read_text()

# v1 SQL — reads total_price (major units) and converts to minor units in Python
_SQL_V1 = """
SELECT date(created_at) AS day, SUM(total_price) AS revenue
FROM orders
WHERE status IN ('PAID', 'SHIPPED')
GROUP BY day
ORDER BY day
"""


def _has_column(conn, table: str, column: str) -> bool:
    """Return True if *column* exists in *table* on the given connection."""
    insp = inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            if _has_column(conn, "orders", "total_minor"):
                # v2 schema: total_minor already in integer minor units
                rows = conn.execute(text(_SQL_V2)).fetchall()
                return [
                    {"day": str(row.day)[:10], "revenue_minor": int(row.revenue)}
                    for row in rows
                ]
            else:
                # v1 schema: total_price is float major units → convert to minor
                from decimal import Decimal

                rows = conn.execute(text(_SQL_V1)).fetchall()
                return [
                    {
                        "day": str(row.day)[:10],
                        "revenue_minor": int(Decimal(str(row.revenue)) * 100),
                    }
                    for row in rows
                ]
    finally:
        engine.dispose()
