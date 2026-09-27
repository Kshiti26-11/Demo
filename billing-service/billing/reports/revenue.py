from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


_SQL_V1 = (Path(__file__).parent / "revenue_v1.sql").read_text()
_SQL_V2 = (Path(__file__).parent / "revenue_v2.sql").read_text()


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _schema_version(conn) -> str:
    try:
        return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar() or "")
    except Exception:
        conn.rollback()
        return ""


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            ver = _schema_version(conn)
            sql = _SQL_V2 if ver >= "0002" else _SQL_V1
            rows = conn.execute(text(sql)).fetchall()
    finally:
        engine.dispose()

    results = []
    for row in rows:
        rev = row.revenue
        if rev is None:
            rev_minor = 0
        elif ver >= "0002":
            rev_minor = int(rev)
        else:
            rev_minor = _round_half_up(Decimal(str(rev)) * 100)
        results.append(
            {
                "day": str(row.day)[:10],
                "revenue_minor": rev_minor,
            }
        )
    return results
