import os

from alembic import context
from sqlalchemy import create_engine, pool

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./orders.db")


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
