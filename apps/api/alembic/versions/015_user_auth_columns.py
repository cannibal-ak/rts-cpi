"""Add authentication columns to app_user table.

Adds password_hash, must_change_password, last_login_at,
failed_login_count, locked_until, password_changed_at for
Phase 2 real JWT authentication.

Revision ID: 015
Revises: 014
Create Date: 2026-04-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("app_user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("app_user", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_user", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("app_user", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_user", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: ensure all existing users must change password on next login
    op.execute("UPDATE app_user SET must_change_password = TRUE WHERE must_change_password IS NULL")


def downgrade() -> None:
    op.drop_column("app_user", "password_changed_at")
    op.drop_column("app_user", "locked_until")
    op.drop_column("app_user", "failed_login_count")
    op.drop_column("app_user", "last_login_at")
    op.drop_column("app_user", "must_change_password")
    op.drop_column("app_user", "password_hash")
