import decimal

import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect, text


@pytest.fixture()
def db_file(monkeypatch, tmp_path):
    db_path = tmp_path / "test_orders.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    return db_url


def test_upgrade_and_downgrade(db_file):
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")

    # Upgrade to 0001 only
    command.upgrade(cfg, "0001")
    engine = create_engine(db_file)

    # Insert two v1 rows
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO orders (order_id, customer_name, total_price, status, created_at) "
            "VALUES ('o-1001', 'Ada Lovelace', 19.99, 'PAID', '2026-09-01T10:00:00+00:00')"
        ))
        conn.execute(text(
            "INSERT INTO orders (order_id, customer_name, total_price, status, created_at) "
            "VALUES ('o-1002', 'Alan Turing', 5.00, 'PENDING', '2026-09-02T11:00:00+00:00')"
        ))
        conn.commit()
    engine.dispose()

    # Upgrade to head (0002)
    command.upgrade(cfg, "head")
    engine = create_engine(db_file)

    with engine.connect() as conn:
        row1 = conn.execute(text("SELECT * FROM orders WHERE order_id = 'o-1001'")).mappings().one()
        assert row1["total_minor"] == 1999
        assert row1["currency"] == "USD"
        assert row1["customer_id"] == "c-1001"
        assert row1["customer_display_name"] == "Ada Lovelace"

        row2 = conn.execute(text("SELECT * FROM orders WHERE order_id = 'o-1002'")).mappings().one()
        assert row2["status"] == "AWAITING_PAYMENT"
    engine.dispose()

    # Downgrade back to 0001
    command.downgrade(cfg, "0001")
    engine = create_engine(db_file)

    with engine.connect() as conn:
        row1 = conn.execute(text("SELECT * FROM orders WHERE order_id = 'o-1001'")).mappings().one()
        assert decimal.Decimal(str(row1["total_price"])) == decimal.Decimal("19.99")

        row2 = conn.execute(text("SELECT * FROM orders WHERE order_id = 'o-1002'")).mappings().one()
        assert row2["status"] == "PENDING"
    engine.dispose()
