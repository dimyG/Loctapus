"""Tests for the worker's embedding dimension guard."""

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.schema_guard import (
    query_embedding_dimension,
    run_startup_checks,
    verify_embedding_dimension,
)
from app.providers import get_embedding_provider


class _MismatchedEmbeddingProvider:
    """Embedding provider whose dimension disagrees with the migrated chunks.embedding column."""

    dimension: int

    def __init__(self, *, dimension: int) -> None:
        """Record the deliberately mismatching dimension."""

        self.dimension = dimension

    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Return zero vectors of the declared dimension."""

        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, *, text: str) -> list[float]:
        """Return a zero vector of the declared dimension."""

        return [0.0] * self.dimension


def test_dimension_guard(*, db_session: Session) -> None:
    """Check the catalog dimension query and the comparison against the provider."""

    assert query_embedding_dimension(db=db_session) == 384
    verify_embedding_dimension(expected_dimension=384, actual_dimension=384)
    pattern = r"vector\(384\).*emits 512.*Alembic migration"
    with pytest.raises(RuntimeError, match=pattern):
        verify_embedding_dimension(expected_dimension=512, actual_dimension=384)
    with pytest.raises(RuntimeError):
        verify_embedding_dimension(expected_dimension=512, actual_dimension=None)


def test_run_startup_checks(*, db_session: Session, settings: Settings) -> None:
    """Check that startup checks pass for a matching provider and fail for a mismatch."""

    run_startup_checks(db=db_session, embedding_provider=get_embedding_provider(settings=settings))
    mismatched = _MismatchedEmbeddingProvider(dimension=512)
    with pytest.raises(RuntimeError, match="512"):
        run_startup_checks(db=db_session, embedding_provider=mismatched)
