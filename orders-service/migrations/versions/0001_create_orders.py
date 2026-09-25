"""create orders table (Orders contract v1)

Revision ID: 0001
Revises:
Create Date: 2026-09-25

Reference copy for SyncSnitch - do not edit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=32), primary_key=True),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("orders")
