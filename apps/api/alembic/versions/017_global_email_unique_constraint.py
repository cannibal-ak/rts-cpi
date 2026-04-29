"""global email unique constraint

Revision ID: 017
Revises: 016
Create Date: 2026-04-29 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint('uq_app_user_email_global', 'app_user', ['email'])


def downgrade() -> None:
    op.drop_constraint('uq_app_user_email_global', 'app_user', type_='unique')
