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
            # Check alembic version table if present
            try:
                res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                version_num = res[0] if res else "0001"
            except Exception:
                version_num = "0001"

            if version_num >= "0002":
                rows = conn.execute(text(_SQL_V2)).fetchall()
                is_minor = True
            else:
                rows = conn.execute(text(_SQL_V1)).fetchall()
                is_minor = False
    finally:
        engine.dispose()

    results = []
    for row in rows:
        rev = row.revenue if row.revenue is not None else 0
        if is_minor:
            revenue_minor = int(rev)
        else:
            revenue_minor = _round_half_up(Decimal(str(rev)) * 100)
        results.append(
            {
                "day": str(row.day)[:10],
                "revenue_minor": revenue_minor,
            }
        )
    return results
