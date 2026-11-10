"""Test fakes shared across the backend suites."""

from app.providers.base import ChatMessage, LLMError, RouteDecision


class MismatchedEmbeddingProvider:
    """Embedding provider whose dimension disagrees with the migrated chunks.embedding column."""

    dimension: int

    def __init__(self, *, dimension: int) -> None:
        """Record the deliberately mismatching dimension.

        :param dimension: Vector width the fake reports instead of the migrated column's.
        """

        self.dimension = dimension

    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Return zero vectors of the declared dimension.

        :param texts: Texts to embed; only their count shapes the returned matrix.
        """

        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, *, text: str) -> list[float]:
        """Return a zero vector of the declared dimension.

        :param text: Query text to embed; ignored beyond keeping the provider protocol.
        """

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
        """Store the fixed responses and flags, and open the call logs.

        :param answer: Text every generate call returns.
        :param route_response: Decision every route call returns when ``route_error`` is false.
        :param route_error: When true, every route call raises instead of answering.
        """

        self.answer = answer
        self.route_response = route_response
        self.route_error = route_error
        self.calls: list[tuple[str, list[ChatMessage]]] = []
        self.route_calls: list[tuple[str, list[ChatMessage]]] = []

    async def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Record one (system, messages) call and return the fixed answer.

        :param system: System prompt the answer call carries.
        :param messages: Message list the answer call carries.
        """

        self.calls.append((system, messages))
        return self.answer

    async def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Record one router call, then raise or return the fixed decision.

        :param system: System prompt the router call carries.
        :param messages: Message list the router call carries.
        """

        self.route_calls.append((system, messages))
        if self.route_error:
            raise LLMError("The router is down for maintenance.")
        if self.route_response is None:
            return RouteDecision(route="retrieve", rewritten_query=None)
        return self.route_response

    async def aclose(self) -> None:
        """Hold no resources, so closing does nothing.

        :param: None.
        """


class RaisingLLMProvider:
    """LLM provider whose every call raises; pins the 502 mapping and the router fallback."""

    async def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Raise the maintenance error every caller maps to a 502.

        :param system: System prompt the call carries; ignored by the raise.
        :param messages: Message list the call carries; ignored by the raise.
        """

        raise LLMError("The answer service is down for maintenance.")

    async def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Raise so the answer service falls back to retrieval with the raw question.

        :param system: System prompt the call carries; ignored by the raise.
        :param messages: Message list the call carries; ignored by the raise.
        """

        raise LLMError("The answer service is down for maintenance.")

    async def aclose(self) -> None:
        """Hold no resources, so closing does nothing.

        :param: None.
        """
