from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


_SQL_V1 = (Path(__file__).parent / "revenue_v1.sql").read_text()
_SQL_V2 = (Path(__file__).parent / "revenue_v2.sql").read_text()


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            try:
                version_res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                version_num = version_res.version_num if version_res else "0001"
            except Exception:
                version_num = "0001"

            if version_num >= "0002":
                rows = conn.execute(text(_SQL_V2)).fetchall()
                return [
                    {
                        "day": str(row.day)[:10],
                        "revenue_minor": int(row.revenue),
                    }
                    for row in rows
                ]
            else:
                # Check if total_minor column exists in orders table
                res = conn.execute(text("PRAGMA table_info(orders)")).fetchall()
                cols = [r[1] for r in res]
                if "total_minor" in cols:
                    rows = conn.execute(text(_SQL_V2)).fetchall()
                    return [
                        {
                            "day": str(row.day)[:10],
                            "revenue_minor": int(row.revenue),
                        }
                        for row in rows
                    ]
                else:
                    rows = conn.execute(text(_SQL_V1)).fetchall()
                    return [
                        {
                            "day": str(row.day)[:10],
                            "revenue_minor": _round_half_up(Decimal(str(row.revenue)) * 100),
                        }
                        for row in rows
                    ]
    finally:
        engine.dispose()
