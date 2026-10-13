"""Stub embedding provider built from a deterministic hash-bag of token vectors."""

import hashlib
import math

# Changing this value requires an Alembic migration re-typing chunks.embedding.
# It also requires re-embedding every stored chunk (backlog 2026-10-12).
# Re-embedding runs from chunks.text, so it needs no re-parse.
STUB_EMBEDDING_DIM = 384


def _hash_bag(*, text: str) -> list[float]:
    """Return the L2-normalized hash-bag vector for ``text``, zeros when empty."""

    vector = [0.0] * STUB_EMBEDDING_DIM
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % STUB_EMBEDDING_DIM
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


class StubEmbeddingProvider:
    """Deterministic hash-bag embeddings for local development and tests."""

    dimension: int = STUB_EMBEDDING_DIM

    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Embed every text into a fixed-dimension vector."""

        return [_hash_bag(text=text) for text in texts]

    def embed_query(self, *, text: str) -> list[float]:
        """Embed a single query text into a fixed-dimension vector."""

        return _hash_bag(text=text)
