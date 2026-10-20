"""query logs schema

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("stages", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # No ON DELETE action: deleting a user must not rewrite a project's query past.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_logs_project_id_created_at", "query_logs", ["project_id", "created_at"])
    op.create_index("ix_query_logs_user_id", "query_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_query_logs_user_id", table_name="query_logs")
    op.drop_index("ix_query_logs_project_id_created_at", table_name="query_logs")
    op.drop_table("query_logs")
