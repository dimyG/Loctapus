"""convert naive timestamps to timestamptz

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table ran on the UTC-configured docker Postgres, so naive values are UTC wall time.
_COLUMNS: tuple[tuple[str, str], ...] = (
    ("users", "created_at"),
    ("projects", "created_at"),
    ("revoked_tokens", "expires_at"),
    ("revoked_tokens", "revoked_at"),
)


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
