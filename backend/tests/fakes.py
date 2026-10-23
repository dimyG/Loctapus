"""Test fakes shared across the backend suites."""

from app.providers.base import ChatMessage, LLMError, RouteDecision


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
    """LLM provider that records every call and returns fixed responses."""

    def __init__(
        self,
        *,
        answer: str,
        route_response: RouteDecision | None = None,
        route_error: bool = False,
    ) -> None:
        """Store the fixed responses and flags, and open the call logs."""

        self.answer = answer
        self.route_response = route_response
        self.route_error = route_error
        self.calls: list[tuple[str, list[ChatMessage]]] = []
        self.route_calls: list[tuple[str, list[ChatMessage]]] = []

    def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Record one (system, messages) call and return the fixed answer."""

        self.calls.append((system, messages))
        return self.answer

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Record one router call, then raise or return the fixed decision."""

        self.route_calls.append((system, messages))
        if self.route_error:
            raise LLMError("The router is down for maintenance.")
        if self.route_response is None:
            return RouteDecision(route="retrieve", rewritten_query=None)
        return self.route_response


class RaisingLLMProvider:
    """LLM provider whose every call raises; pins the 502 mapping and the router fallback."""

    def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Raise the maintenance error every caller maps to a 502."""

        raise LLMError("The answer service is down for maintenance.")

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Raise so the answer service falls back to retrieval with the raw question."""

        raise LLMError("The answer service is down for maintenance.")
