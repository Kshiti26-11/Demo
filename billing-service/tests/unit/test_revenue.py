import tempfile
import os

import pytest
from sqlalchemy import create_engine, text

from billing.reports.revenue import run_revenue_report

ROWS = [
    ("o-1001", "Ada Lovelace",    19.99, "PAID",      "2026-09-01 10:00:00"),
    ("o-1002", "Alan Turing",      5.0,  "PENDING",   "2026-09-02 11:00:00"),
    ("o-1003", "Grace Hopper",   120.5,  "SHIPPED",   "2026-09-03 12:00:00"),
    ("o-1004", "Edsger Dijkstra", 42.0,  "CANCELLED", "2026-09-04 13:00:00"),
]

EXPECTED = [
    {"day": "2026-09-01", "revenue_minor": 1999},
    {"day": "2026-09-03", "revenue_minor": 12050},
]


@pytest.fixture
def db_url(tmp_path):
    db_file = tmp_path / "test_orders.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                order_id TEXT,
                customer_name TEXT,
                total_price NUMERIC,
                status TEXT,
                created_at TEXT
            )
        """))
        for row in ROWS:
            conn.execute(
                text("INSERT INTO orders VALUES (:a, :b, :c, :d, :e)"),
                {"a": row[0], "b": row[1], "c": row[2], "d": row[3], "e": row[4]},
            )
        conn.commit()
    engine.dispose()
    return url


def test_revenue_report(db_url):
    result = run_revenue_report(db_url)
    assert result == EXPECTED
