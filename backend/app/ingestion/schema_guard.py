"""The worker's embedding dimension guard, split from the pipeline services.

The guard compares the selected provider's dimension against the migrated catalog
type and refuses to start on mismatch, before any chunk row is written.
"""

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.base import EmbeddingProvider

# The catalog type of chunks.embedding looks like vector(384); the guard parses the dimension.
_VECTOR_TYPE_PATTERN = re.compile(r"^vector\((\d+)\)$")


def query_embedding_dimension(*, db: Session) -> int | None:
    """Return the vector dimension of the chunks.embedding column, or None when absent.

    Reading the catalog type catches schema drift without loading any chunk rows, and
    None also covers a column that is not a fixed-dimension vector. ``to_regclass``
    resolves the table through the search path, so a same-named table in another
    schema cannot satisfy the lookup.
    """

    data_type = db.scalar(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass('chunks') AND a.attname = 'embedding' "
            "AND a.attnum > 0 AND NOT a.attisdropped"
        )
    )
    if data_type is None:
        return None
    match = _VECTOR_TYPE_PATTERN.match(str(data_type))
    return int(match.group(1)) if match is not None else None


def verify_embedding_dimension(*, expected_dimension: int, actual_dimension: int | None) -> None:
    """Raise when the stored column dimension disagrees with the provider's.

    Failing fast here replaces a cryptic psycopg insert failure deep in the embed path
    after chunks are already committed.
    """

    if actual_dimension != expected_dimension:
        raise RuntimeError(
            f"chunks.embedding is vector({actual_dimension}) but the selected provider "
            f"emits {expected_dimension}; changing the dimension requires an Alembic migration"
        )


def run_startup_checks(*, db: Session, embedding_provider: EmbeddingProvider) -> None:
    """Run the worker's startup checks: query the catalog and verify the dimension."""

    verify_embedding_dimension(
        expected_dimension=embedding_provider.dimension,
        actual_dimension=query_embedding_dimension(db=db),
    )
