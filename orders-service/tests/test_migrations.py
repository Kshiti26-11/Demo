import os
import tempfile

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


def test_upgrade_head_columns(db_file):
    # Run alembic upgrade head
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    command.upgrade(cfg, "head")

    engine = create_engine(db_file)
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("orders")}
    assert columns == {"order_id", "customer_name", "total_price", "status", "created_at"}
    engine.dispose()
