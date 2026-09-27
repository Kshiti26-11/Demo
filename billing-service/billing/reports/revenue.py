from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            try:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except OperationalError:
                version = "0001"

            if version >= "0002":
                sql = (Path(__file__).parent / "revenue_v2.sql").read_text()
                rows = conn.execute(text(sql)).fetchall()
                return [
                    {
                        "day": str(row.day)[:10],
                        "revenue_minor": int(row.revenue),
                    }
                    for row in rows
                ]
            else:
                sql = (Path(__file__).parent / "revenue_v1.sql").read_text()
                rows = conn.execute(text(sql)).fetchall()
                return [
                    {
                        "day": str(row.day)[:10],
                        "revenue_minor": _round_half_up(Decimal(str(row.revenue)) * 100),
                    }
                    for row in rows
                ]
    finally:
        engine.dispose()
