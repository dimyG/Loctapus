"""Provider interfaces shared by the parse and embed pipelines."""

from dataclasses import dataclass
from typing import Protocol


class ParseError(Exception):
    """Raised when a parser cannot extract a usable document; its message is shown to users."""


@dataclass
class NormalizedElement:
    """One extractable content block from a parsed document."""

    type: str
    text: str
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
        """Parse raw document bytes into a normalized document."""

        ...


class EmbeddingProvider(Protocol):
    """Interface every embedding provider implements."""

    dimension: int

    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into fixed-dimension vectors."""

        ...

    def embed_query(self, *, text: str) -> list[float]:
        """Embed a single query text into a fixed-dimension vector."""

        ...


class LLMError(Exception):
    """Raised when an LLM provider cannot generate; its message is shown to users."""


class LLMProvider(Protocol):
    """Interface every LLM provider implements."""

    def generate(self, *, system: str, user: str) -> str:
        """Generate one completion from a system prompt and a user prompt."""

        ...
