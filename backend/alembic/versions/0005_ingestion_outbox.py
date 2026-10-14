"""ingestion and outbox schema

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Indexes that no composite unique constraint already covers by its leading column:
# source_items.source_id, documents.source_item_id, and chunks.document_id lead their
# composite uniques, so they are skipped as redundant.
_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sources", ("project_id",)),
    ("chunks", ("project_id",)),
    ("ingestion_runs", ("document_id",)),
    ("ingestion_runs", ("source_item_id", "created_at", "id")),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("type IN ('upload')"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Exists only as the unique target the composite FK below requires.
        sa.UniqueConstraint("id", "project_id", name="uq_sources_id_project_id"),
    )
    op.create_table(
        "source_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        # project_id is repeated down the chain so retrieval filters by project without
        # joins, and the composite FK below makes the database reject any row whose
        # project differs from its source's.
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("raw_object_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["sources.id", "sources.project_id"],
            ondelete="CASCADE",
            name="fk_source_items_source_id_project_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id"),
        sa.CheckConstraint("size_bytes > 0"),
        sa.UniqueConstraint("id", "project_id", name="uq_source_items_id_project_id"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        # project_id is repeated down the chain so retrieval filters by project without
        # joins, and the composite FK below makes the database reject any row whose
        # project differs from its item's.
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("raw_object_key", sa.String(), nullable=False),
        sa.Column("normalized_content", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            ondelete="CASCADE",
            name="fk_documents_source_item_id_project_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id", "content_hash"),
        sa.UniqueConstraint("id", "project_id", name="uq_documents_id_project_id"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("heading_path", postgresql.JSONB(), nullable=False),
        sa.Column("chunk_type", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        # The dimension is the hardcoded STUB_EMBEDDING_DIM literal: a migration never reads
        # a runtime value, so one revision builds one schema in every environment.
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
        ),
        sa.CheckConstraint("chunk_type IN ('text')"),
        # project_id is repeated down the chain so retrieval filters chunks by project
        # without joins, and the composite FK makes the database reject any row whose
        # project differs from its document's.
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            ondelete="CASCADE",
            name="fk_chunks_document_id_project_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "position"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        # The file version the run was created for: the worker fetches by this key and
        # verifies the fetched bytes against this hash.
        sa.Column("raw_object_key", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'fetching', 'processing', 'indexing', 'ready', 'failed')"),
        # finished_at must exist exactly when the run reached a terminal status, so a
        # finished run is never mistaken for one still in flight and vice versa.
        sa.CheckConstraint("(status IN ('ready', 'failed')) = (finished_at IS NOT NULL)"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for table, columns in _INDEXES:
        op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns))
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")
    # The outbox poller scans unpublished events oldest first; published rows leave the index.
    op.create_index(
        "ix_outbox_events_created_at_unpublished",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_created_at_unpublished", table_name="outbox_events")
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.drop_index("ix_ingestion_runs_source_item_id_created_at_id", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_document_id", table_name="ingestion_runs")
    op.drop_index("ix_chunks_project_id", table_name="chunks")
    op.drop_index("ix_sources_project_id", table_name="sources")
    op.drop_table("outbox_events")
    op.drop_table("ingestion_runs")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("source_items")
    op.drop_table("sources")
    op.execute("DROP EXTENSION IF EXISTS vector")
