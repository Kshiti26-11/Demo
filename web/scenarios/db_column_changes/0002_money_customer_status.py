"""money in minor units, structured customer, payment-state rename (Orders contract v2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

- adds total_minor (BIGINT, = total_price * 100), currency (default USD),
  customer_id (derived: 'c-' || digits of order_id), shipping_eta (nullable)
- renames customer_name -> customer_display_name
- drops total_price
- data migration: status PENDING -> AWAITING_PAYMENT

Uses batch mode so it runs on SQLite (tests) and PostgreSQL (containers).
Reference copy for SyncSnitch - do not edit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("total_minor", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD")
        )
        batch_op.add_column(sa.Column("customer_id", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("shipping_eta", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column(
            "customer_name",
            new_column_name="customer_display_name",
            existing_type=sa.String(length=200),
            existing_nullable=False,
        )
    op.execute("UPDATE orders SET total_minor = CAST(ROUND(total_price * 100) AS BIGINT)")
    op.execute("UPDATE orders SET customer_id = 'c-' || SUBSTR(order_id, 3)")
    op.execute("UPDATE orders SET status = 'AWAITING_PAYMENT' WHERE status = 'PENDING'")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("total_minor", existing_type=sa.BigInteger(), nullable=False)
        batch_op.alter_column("customer_id", existing_type=sa.String(length=32), nullable=False)
        batch_op.drop_column("total_price")


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("total_price", sa.Numeric(10, 2), nullable=True))
    op.execute("UPDATE orders SET total_price = total_minor / 100.0")
    op.execute("UPDATE orders SET status = 'PENDING' WHERE status = 'AWAITING_PAYMENT'")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column("total_price", existing_type=sa.Numeric(10, 2), nullable=False)
        batch_op.alter_column(
            "customer_display_name",
            new_column_name="customer_name",
            existing_type=sa.String(length=200),
            existing_nullable=False,
        )
        batch_op.drop_column("shipping_eta")
        batch_op.drop_column("customer_id")
        batch_op.drop_column("currency")
        batch_op.drop_column("total_minor")
