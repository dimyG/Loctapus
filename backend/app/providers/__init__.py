"""Provider interfaces, stub implementations, and the string-based factories."""

from app.core.config import Settings
from app.providers.base import EmbeddingProvider, NormalizedDocument, NormalizedElement, Parser
from app.providers.stub_embeddings import STUB_EMBEDDING_DIM, StubEmbeddingProvider
from app.providers.stub_parser import StubParser

__all__ = [
    "EmbeddingProvider",
    "NormalizedDocument",
    "NormalizedElement",
    "Parser",
    "STUB_EMBEDDING_DIM",
    "StubEmbeddingProvider",
    "StubParser",
    "get_embedding_provider",
    "get_parser",
]


def get_parser(*, settings: Settings) -> Parser:
    """Return the parser provider selected by ``settings.parser_provider``."""

    if settings.parser_provider == "stub":
        return StubParser()
    raise ValueError(f"unknown parser_provider: {settings.parser_provider!r}")


def get_embedding_provider(*, settings: Settings) -> EmbeddingProvider:
    """Return the embedding provider selected by ``settings.embedding_provider``."""

    if settings.embedding_provider == "stub":
        return StubEmbeddingProvider()
    raise ValueError(f"unknown embedding_provider: {settings.embedding_provider!r}")
