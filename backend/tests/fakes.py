"""Test fakes shared across the backend suites."""

from app.providers.base import LLMError


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


class RecordingLLMProvider:
    """LLM provider that records every call and returns a fixed answer."""

    def __init__(self, *, answer: str) -> None:
        """Store the fixed answer to return and open the call log."""

        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system: str, user: str) -> str:
        """Record one (system, user) call and return the fixed answer."""

        self.calls.append((system, user))
        return self.answer


class RaisingLLMProvider:
    """LLM provider whose every generation raises; pins the 502 mapping."""

    def generate(self, *, system: str, user: str) -> str:
        """Raise the maintenance error every caller maps to a 502."""

        raise LLMError("The answer service is down for maintenance.")
