from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from sqlalchemy import create_engine, text

def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    sql_path = Path(__file__).parent / "revenue.sql"
    sql = sql_path.read_text(encoding="utf-8")
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    engine.dispose()
    return [
        {
            "day": str(row.day)[:10],
            "revenue_minor": int((Decimal(str(row.revenue)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        }
        for row in rows
    ]
