import pytest
from sqlalchemy import create_engine, text

from billing.reports.revenue import run_revenue_report

# v1 schema: total_price column (major units float)
ROWS_V1 = [
    ("o-1001", "Ada Lovelace",    19.99, "PAID",             "2026-09-01 10:00:00"),
    ("o-1002", "Alan Turing",      5.0,  "PENDING",          "2026-09-02 11:00:00"),
    ("o-1003", "Grace Hopper",   120.5,  "SHIPPED",          "2026-09-03 12:00:00"),
    ("o-1004", "Edsger Dijkstra", 42.0,  "CANCELLED",        "2026-09-04 13:00:00"),
]

# v2 schema: total_minor column (integer minor units), status AWAITING_PAYMENT
ROWS_V2 = [
    ("o-1001", "Ada Lovelace",    1999, "PAID",              "2026-09-01 10:00:00"),
    ("o-1002", "Alan Turing",      500, "AWAITING_PAYMENT",  "2026-09-02 11:00:00"),
    ("o-1003", "Grace Hopper",  12050, "SHIPPED",            "2026-09-03 12:00:00"),
    ("o-1004", "Edsger Dijkstra", 4200, "CANCELLED",         "2026-09-04 13:00:00"),
]

EXPECTED = [
    {"day": "2026-09-01", "revenue_minor": 1999},
    {"day": "2026-09-03", "revenue_minor": 12050},
]


@pytest.fixture
def db_url_v1(tmp_path):
    """v1 schema — has total_price, no total_minor."""
    db_file = tmp_path / "test_orders_v1.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                order_id TEXT,
                customer_display_name TEXT,
                total_price NUMERIC,
                status TEXT,
                created_at TEXT
            )
        """))
        for row in ROWS_V1:
            conn.execute(
                text("INSERT INTO orders VALUES (:a, :b, :c, :d, :e)"),
                {"a": row[0], "b": row[1], "c": row[2], "d": row[3], "e": row[4]},
            )
        conn.commit()
    engine.dispose()
    return url


@pytest.fixture
def db_url_v2(tmp_path):
    """v2 schema — has total_minor, customer_display_name, AWAITING_PAYMENT status."""
    db_file = tmp_path / "test_orders_v2.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE orders (
                order_id TEXT,
                customer_display_name TEXT,
                total_minor INTEGER,
                status TEXT,
                created_at TEXT
            )
        """))
        for row in ROWS_V2:
            conn.execute(
                text("INSERT INTO orders VALUES (:a, :b, :c, :d, :e)"),
                {"a": row[0], "b": row[1], "c": row[2], "d": row[3], "e": row[4]},
            )
        conn.commit()
    engine.dispose()
    return url


def test_revenue_report_v1_schema(db_url_v1):
    """Old schema (total_price): SQL falls back to total_price*100."""
    result = run_revenue_report(db_url_v1)
    assert result == EXPECTED


def test_revenue_report_v2_schema(db_url_v2):
    """New schema (total_minor): SQL reads total_minor directly."""
    result = run_revenue_report(db_url_v2)
    assert result == EXPECTED
