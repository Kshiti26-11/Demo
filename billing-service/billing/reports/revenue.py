from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            has_alembic = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )).fetchone()

            if has_alembic:
                res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                version_num = res[0] if res else "0001"
            else:
                rows_info = conn.execute(text("PRAGMA table_info(orders)")).fetchall()
                cols = [r[1] for r in rows_info]
                if "total_minor" in cols:
                    version_num = "0002"
                else:
                    version_num = "0001"

            if version_num >= "0002":
                sql_path = Path(__file__).parent / "revenue_v2.sql"
            else:
                sql_path = Path(__file__).parent / "revenue_v1.sql"
            _SQL = sql_path.read_text()
            rows = conn.execute(text(_SQL)).fetchall()
    finally:
        engine.dispose()

    if version_num >= "0002":
        return [
            {
                "day": str(row.day)[:10],
                "revenue_minor": int(row.revenue),
            }
            for row in rows
        ]
    else:
        return [
            {
                "day": str(row.day)[:10],
                "revenue_minor": _round_half_up(Decimal(str(row.revenue)) * 100),
            }
            for row in rows
        ]
