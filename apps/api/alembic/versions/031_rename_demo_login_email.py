"""Rename demo tenant login email alt@airline.com -> skyair@airline.com.

Idempotent data migration for the Sky Airways DEMO tenant created in 030.
Only the login email changes; password, display_name, tenant slug ('alt'),
and the Demo_Admin role label are all left untouched.

Revision ID: 031
Revises: 030
Create Date: 2026-06-05
"""
from typing import Sequence, Union
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE app_user SET email='skyair@airline.com' "
        "WHERE email='alt@airline.com'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE app_user SET email='alt@airline.com' "
        "WHERE email='skyair@airline.com'"
    )
