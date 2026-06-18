"""Add invite tokens + hash reset codes on password_reset_token.

- purpose: distinguishes 'reset' vs 'invite' tokens.
- token_hash: sha256 hex of the code/token; replaces plaintext code at rest.
- code: made nullable (new rows store only the hash).
- idx_reset_token_code dropped (codes no longer queried in plaintext);
  new indexes on token_hash and (email, purpose).

Revision: 032
Revises: 031
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "password_reset_token",
        sa.Column("purpose", sa.String(16), nullable=False, server_default=sa.text("'reset'")),
    )
    op.add_column(
        "password_reset_token",
        sa.Column("token_hash", sa.String(64), nullable=True),
    )
    op.alter_column("password_reset_token", "code", nullable=True)
    op.drop_index("idx_reset_token_code", table_name="password_reset_token")
    op.create_index("idx_reset_token_hash", "password_reset_token", ["token_hash"])
    op.create_index("idx_reset_token_email_purpose", "password_reset_token", ["email", "purpose"])


def downgrade() -> None:
    op.drop_index("idx_reset_token_email_purpose", table_name="password_reset_token")
    op.drop_index("idx_reset_token_hash", table_name="password_reset_token")
    op.create_index("idx_reset_token_code", "password_reset_token", ["code"])
    # Backfill any NULL codes before restoring the NOT NULL constraint.
    op.execute("UPDATE password_reset_token SET code = '000000' WHERE code IS NULL")
    op.alter_column("password_reset_token", "code", nullable=False)
    op.drop_column("password_reset_token", "token_hash")
    op.drop_column("password_reset_token", "purpose")
