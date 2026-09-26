from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


_SQL = (Path(__file__).parent / "revenue.sql").read_text()


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(_SQL)).fetchall()
    finally:
        engine.dispose()

    return [
        {
            "day": str(row.day)[:10],
            "revenue_minor": _round_half_up(Decimal(str(row.revenue)) * 100),
        }
        for row in rows
    ]
