"""Provider interfaces, stub implementations, and the string-based factories."""

from typing import assert_never

from app.core.config import Settings
from app.providers.base import (
    EmbeddingProvider,
    LLMError,
    LLMProvider,
    NormalizedDocument,
    NormalizedElement,
    ParseError,
    Parser,
)
from app.providers.stub_embeddings import STUB_EMBEDDING_DIM, StubEmbeddingProvider
from app.providers.stub_llm import STUB_ANSWER, StubLLMProvider
from app.providers.stub_parser import StubParser

__all__ = [
    "EmbeddingProvider",
    "LLMError",
    "LLMProvider",
    "NormalizedDocument",
    "NormalizedElement",
    "ParseError",
    "Parser",
    "STUB_ANSWER",
    "STUB_EMBEDDING_DIM",
    "StubEmbeddingProvider",
    "StubLLMProvider",
    "StubParser",
    "get_embedding_provider",
    "get_llm_provider",
    "get_parser",
]


def get_parser(*, settings: Settings) -> Parser:
    """Return the parser provider selected by ``settings.parser_provider``.

    The setting is a ``Literal`` and this match is exhaustive, so an unresolvable
    provider is a settings-construction error (fail fast at boot), never a runtime
    branch here.
    """

    match settings.parser_provider:
        case "stub":
            return StubParser()
        case _ as unreachable:
            assert_never(unreachable)


def get_embedding_provider(*, settings: Settings) -> EmbeddingProvider:
    """Return the embedding provider selected by ``settings.embedding_provider``.

    The setting is a ``Literal`` and this match is exhaustive, so an unresolvable
    provider is a settings-construction error (fail fast at boot), never a runtime
    branch here.
    """

    match settings.embedding_provider:
        case "stub":
            return StubEmbeddingProvider()
        case _ as unreachable:
            assert_never(unreachable)


def get_llm_provider(*, settings: Settings) -> LLMProvider:
    """Return the LLM provider selected by ``settings.llm_provider``.

    The setting is a ``Literal`` and this match is exhaustive, so an unresolvable
    provider is a settings-construction error (fail fast at boot), never a runtime
    branch here.
    """

    match settings.llm_provider:
        case "stub":
            return StubLLMProvider()
        case _ as unreachable:
            assert_never(unreachable)
