"""Provider interfaces every parser, embedding, and LLM implementation shares.

These are ``Protocol`` classes: implementations satisfy them structurally and
do not inherit from them. Ingestion uses ``Parser`` and ``EmbeddingProvider``,
retrieval uses ``EmbeddingProvider``, and answers uses ``LLMProvider``.
"""

from dataclasses import dataclass
from typing import Literal, Protocol


class ParseError(Exception):
    """Raised when a parser cannot extract a usable document; its message is shown to users."""


@dataclass
class NormalizedElement:
    """One extractable content block from a parsed document."""

    type: str
    text: str
    # Only headings carry a level; chunking reads it to build the heading path.
    level: int | None = None


@dataclass
class NormalizedDocument:
    """The parse result every parser provider returns."""

    title: str
    elements: list[NormalizedElement]
    metadata: dict[str, str]


class Parser(Protocol):
    """Interface every parser provider implements."""

    def parse(self, *, filename: str, content: bytes) -> NormalizedDocument:
        """Parse raw document bytes into a normalized document.

        The filename suffix, not the bytes, selects the format. Raises
        ``ParseError`` with user-safe copy when nothing usable comes out.

        :param filename: Upload name whose suffix selects the format.
        :param content: Raw file bytes to extract text from.
        """

        ...


class EmbeddingProvider(Protocol):
    """Interface every embedding provider implements."""

    # The worker's startup guard compares this to the chunks.embedding column
    # type and refuses to boot on a mismatch.
    dimension: int

    # Queries and passages stay separate methods so a real provider can treat
    # them differently without changing callers; the stub shares one body.
    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into fixed-dimension vectors.

        :param texts: Texts to embed, in the order the vectors come back.
        """

        ...

    def embed_query(self, *, text: str) -> list[float]:
        """Embed a single query text into a fixed-dimension vector.

        :param text: Query text to embed.
        """

        ...


class LLMError(Exception):
    """Raised when an LLM provider cannot generate; its message is shown to users."""


@dataclass
class ChatMessage:
    """One chat turn sent to an LLM provider, in send order."""

    # The system prompt is a generate/route parameter, never a message role.
    role: Literal["user", "assistant"]
    content: str


@dataclass
class RouteDecision:
    """The router's choice of which evidence path one answer turn takes."""

    route: Literal["direct", "reuse", "retrieve"]
    # On retrieve this is the standalone search question; None searches the
    # raw question. On direct and reuse the field is not applicable.
    rewritten_query: str | None


class LLMProvider(Protocol):
    """Interface every LLM provider implements.

    Unlike ``Parser`` and ``EmbeddingProvider``, this interface is async: an LLM
    call waits on the network for seconds, so it must not hold a threadpool
    thread while it waits.
    """

    async def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Generate one completion from a system prompt and the chat turns.

        Raises ``LLMError`` with user-safe copy on any upstream failure.

        :param system: System prompt steering the completion.
        :param messages: Prior turns in send order, oldest first.
        """

        ...

    async def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Choose the answer path for one turn from the router prompt and the turns.

        Raises ``LLMError`` with user-safe copy when the reply breaks the
        router contract; the answer service then falls back to a retrieve turn.

        :param system: Router prompt naming the three paths.
        :param messages: Prior turns in send order, oldest first.
        """

        ...

    async def aclose(self) -> None:
        """Release the provider's network resources.

        The application lifespan calls this once, at shutdown.
        """
