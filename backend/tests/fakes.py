"""Test fakes shared across the backend suites."""


class MismatchedEmbeddingProvider:
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
