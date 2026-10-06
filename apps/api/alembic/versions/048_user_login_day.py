"""user_login_day — one row per user per day of sign-in activity.

Backs the admin Login Activity page: first/last login of the day, how many
logins, the last explicit logout, and a last-seen stamp kept fresh by
/auth/refresh and the browser heartbeat (most sessions end by closing the
tab, which never calls /logout).

Short retention by design: the app prunes rows older than
LOGIN_ACTIVITY_RETENTION_DAYS on each login, so there is no long-term
history and no beat job. activity_date is the IST calendar day.

Not audit_event on purpose — admin_password_management._has_activity_history
treats any audit row as history that blocks hard-delete; this table cascades
with the user instead.

Pure SQL, no app imports (040's rule).

Revision ID: 048
Revises: 047
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE user_login_day (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id      UUID        NOT NULL REFERENCES tenant(id)   ON DELETE CASCADE,
            user_id        UUID        NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            activity_date  DATE        NOT NULL,
            first_login_at TIMESTAMPTZ NOT NULL,
            last_login_at  TIMESTAMPTZ NOT NULL,
            login_count    INTEGER     NOT NULL DEFAULT 1,
            last_logout_at TIMESTAMPTZ NULL,
            last_seen_at   TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_user_login_day_user_date UNIQUE (user_id, activity_date)
        )
    """)
    # Day listing + retention prune.
    op.create_index("ix_user_login_day_date", "user_login_day", ["activity_date"])
    op.create_index("ix_user_login_day_tenant", "user_login_day", ["tenant_id"])

    # RLS — 002's predicate (coalesce/nullif), same as 040's alert_event_read.
    op.execute("ALTER TABLE user_login_day ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_login_day FORCE  ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY rls_user_login_day_tenant_isolation ON user_login_day
            USING (
                tenant_id::text = coalesce(
                    nullif(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            )
            WITH CHECK (
                tenant_id::text = coalesce(
                    nullif(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            );
    """)
    op.execute("""
        CREATE POLICY rls_user_login_day_superuser_bypass ON user_login_day
            TO cpi USING (true) WITH CHECK (true);
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON user_login_day TO cpi_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_login_day")
