"""Password reset tokens table — 6-digit codes with expiry and attempt tracking.

Adds password_reset_token to support the forgot-password flow.
- Codes are 6-digit numeric strings stored as plain text (5-min expiry +
  attempt limit makes hashing low-value; matches the per-token attempt
  contract in routers/password_reset.py).
- ip_address is logged for audit.
- ON DELETE CASCADE keeps the table in step with app_user deletions.

Revision: 025
Revises: 024
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )
    op.create_index("idx_reset_token_email", "password_reset_token", ["email"])
    op.create_index("idx_reset_token_code", "password_reset_token", ["code"])


def downgrade() -> None:
    op.drop_index("idx_reset_token_code", table_name="password_reset_token")
    op.drop_index("idx_reset_token_email", table_name="password_reset_token")
    op.drop_table("password_reset_token")
