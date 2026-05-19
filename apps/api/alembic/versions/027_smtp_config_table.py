"""SMTP config table — one-row platform settings for outbound email.

Adds the ``smtp_config`` table that backs the admin "Settings → Email"
page. Stores SMTP host/port/credentials so the forgot-password flow
(and any future transactional email) can deliver real messages
instead of relying on the ``admin_debug_code`` fallback.

Single-row table (platform-level scope). The
``uq_smtp_config_single_row`` unique expression-index on ``(true)``
blocks a second insert. When per-tenant overrides eventually arrive,
replace it with a unique index on ``(tenant_id)`` and let NULL
``tenant_id`` mean the platform-wide default row.

``password_encrypted`` holds the SMTP password ciphertext, encrypted
with Fernet using ``CPI_SMTP_ENCRYPTION_KEY`` from the environment.
The plaintext password is never persisted and is never returned by
any read endpoint.

Revision: 027
Revises: 026
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "smtp_config",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column(
            "port",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("587"),
        ),
        # Allowed values: 'NONE' | 'STARTTLS' | 'SSL_TLS'. Enforced by
        # the Pydantic schema; no DB CHECK so the migration stays
        # narrow and the allowed set is easy to extend in code.
        sa.Column(
            "encryption",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'STARTTLS'"),
        ),
        sa.Column("username", sa.String(255), nullable=False),
        # Fernet ciphertext (base64-urlsafe). Never returned to clients.
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("from_email", sa.String(255), nullable=False),
        sa.Column("from_name", sa.String(255), nullable=False),
        # Last-test telemetry. NULL ⇒ never tested.
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        # Allowed values: 'success' | 'failed'. NULL ⇒ never tested.
        sa.Column("last_test_status", sa.String(20), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Loose pointer (no FK). If a platform admin row is ever
        # deleted, this becomes a dead UUID, which is acceptable:
        # the field is rewritten on every save and self-heals on
        # the next update.
        sa.Column("updated_by_user_id", UUID(as_uuid=True), nullable=True),
    )
    # Singleton enforcement: a unique expression index on (true)
    # gives every row the same indexed value, so the unique
    # constraint blocks a second insert.
    op.create_index(
        "uq_smtp_config_single_row",
        "smtp_config",
        [sa.text("(true)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_smtp_config_single_row", table_name="smtp_config")
    op.drop_table("smtp_config")
