from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import create_engine, text


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run_revenue_report(db_url: str) -> list[dict]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            # check alembic version
            v_row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            version_num = v_row.version_num if v_row else "0001"
            is_v2 = version_num >= "0002"
            
            sql_file = "revenue_v2.sql" if is_v2 else "revenue_v1.sql"
            sql = (Path(__file__).parent / sql_file).read_text()
            rows = conn.execute(text(sql)).fetchall()
    except Exception:
        # fallback if alembic_version table doesn't exist
        sql = (Path(__file__).parent / "revenue_v1.sql").read_text()
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
            is_v2 = False
    finally:
        engine.dispose()

    results = []
    for row in rows:
        rev = row.revenue if row.revenue is not None else 0
        if is_v2:
            rev_minor = int(rev)
        else:
            rev_minor = _round_half_up(Decimal(str(rev)) * 100)
        results.append({
            "day": str(row.day)[:10],
            "revenue_minor": rev_minor,
        })
    return results
