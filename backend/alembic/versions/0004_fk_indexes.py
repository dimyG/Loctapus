"""index foreign key columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres does not create indexes for foreign keys, and joins and membership lookups
# filter on these columns; the composite unique constraints cover only the leading
# team_id/project_id columns.
_INDEXES: tuple[tuple[str, str], ...] = (
    ("workspaces", "owner_user_id"),
    ("teams", "workspace_id"),
    ("projects", "workspace_id"),
    ("team_memberships", "user_id"),
    ("project_team_roles", "team_id"),
)


def upgrade() -> None:
    for table, column in _INDEXES:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, column in _INDEXES:
        op.drop_index(f"ix_{table}_{column}", table_name=table)
