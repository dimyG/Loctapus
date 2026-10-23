"""conversations schema and the query->retrieve log rename

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres keeps index names on a table rename, so rename them explicitly to the
    # names the renamed ORM model declares; otherwise schema and metadata disagree.
    op.rename_table("query_logs", "retrieve_logs")
    op.execute(
        "ALTER INDEX ix_query_logs_project_id_created_at RENAME TO ix_retrieve_logs_project_id_created_at"
    )
    op.execute("ALTER INDEX ix_query_logs_user_id RENAME TO ix_retrieve_logs_user_id")
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "last_message_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # No ON DELETE action: deleting a user must not rewrite a project's chat past.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')"),
        # The route marks the router's path; it exists exactly on assistant messages.
        sa.CheckConstraint("(role = 'user') = (route IS NULL)"),
        sa.CheckConstraint("route IN ('direct', 'reuse', 'retrieve')"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "position"),
    )
    op.create_table(
        "conversation_message_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        # SET NULL keeps the snapshot alive when re-ingestion replaces the cited chunk.
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("heading_path", postgresql.JSONB(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("document_content_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["conversation_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "ordinal"),
    )
    op.create_index(
        "ix_conversations_project_id_user_id_last_message_at",
        "conversations",
        ["project_id", "user_id", "last_message_at"],
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversation_message_chunks_chunk_id", "conversation_message_chunks", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_message_chunks_chunk_id", table_name="conversation_message_chunks")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index(
        "ix_conversations_project_id_user_id_last_message_at",
        table_name="conversations",
    )
    op.drop_table("conversation_message_chunks")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.execute(
        "ALTER INDEX ix_retrieve_logs_project_id_created_at RENAME TO ix_query_logs_project_id_created_at"
    )
    op.execute("ALTER INDEX ix_retrieve_logs_user_id RENAME TO ix_query_logs_user_id")
    op.rename_table("retrieve_logs", "query_logs")
