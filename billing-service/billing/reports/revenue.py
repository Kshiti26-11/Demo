from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            version = "0001"
            try:
                row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                if row:
                    version = row[0]
            except Exception:
                pass

            sql_file = "revenue_v2.sql" if version >= "0002" else "revenue_v1.sql"
            sql = (Path(__file__).parent / sql_file).read_text()
            rows = conn.execute(text(sql)).fetchall()
    finally:
        engine.dispose()

    is_v2 = version >= "0002"
    return [
        {
            "day": str(row.day)[:10],
            "revenue_minor": int(row.revenue) if is_v2 else _round_half_up(Decimal(str(row.revenue)) * 100),
        }
        for row in rows
    ]
