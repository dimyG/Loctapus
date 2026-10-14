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
from tests.fakes import MismatchedEmbeddingProvider


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
    mismatched = MismatchedEmbeddingProvider(dimension=512)
    with pytest.raises(RuntimeError, match="512"):
        run_startup_checks(db=db_session, embedding_provider=mismatched)
