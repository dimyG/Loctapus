"""Provider interfaces, the stub and Groq implementations, and the string-based factories."""

from typing import assert_never

from app.core.config import Settings
from app.providers.base import (
    ChatMessage,
    EmbeddingProvider,
    LLMError,
    LLMProvider,
    NormalizedDocument,
    NormalizedElement,
    ParseError,
    Parser,
    RouteDecision,
)
from app.providers.groq_llm import GROQ_ERROR_COPY, GroqLLMProvider
from app.providers.stub_embeddings import STUB_EMBEDDING_DIM, StubEmbeddingProvider
from app.providers.stub_llm import STUB_ANSWER, StubLLMProvider
from app.providers.stub_parser import StubParser

__all__ = [
    "ChatMessage",
    "EmbeddingProvider",
    "GROQ_ERROR_COPY",
    "GroqLLMProvider",
    "LLMError",
    "LLMProvider",
    "NormalizedDocument",
    "NormalizedElement",
    "ParseError",
    "Parser",
    "RouteDecision",
    "STUB_ANSWER",
    "STUB_EMBEDDING_DIM",
    "StubEmbeddingProvider",
    "StubLLMProvider",
    "StubParser",
    "get_embedding_provider",
    "get_llm_provider",
    "get_parser",
]


# Every factory below dispatches on a ``Literal`` settings field, so each match
# is exhaustive: an unresolvable provider is a settings-construction error
# (fail fast at boot), never a runtime branch here.
def get_parser(*, settings: Settings) -> Parser:
    """Return the parser provider selected by ``settings.parser_provider``.

    :param settings: Settings whose ``parser_provider`` literal selects the implementation.
    """

    match settings.parser_provider:
        case "stub":
            return StubParser()
        case _ as unreachable:
            assert_never(unreachable)


def get_embedding_provider(*, settings: Settings) -> EmbeddingProvider:
    """Return the embedding provider selected by ``settings.embedding_provider``.

    :param settings: Settings whose ``embedding_provider`` literal selects the implementation.
    """

    match settings.embedding_provider:
        case "stub":
            return StubEmbeddingProvider()
        case _ as unreachable:
            assert_never(unreachable)


def get_llm_provider(*, settings: Settings) -> LLMProvider:
    """Return the LLM provider selected by ``settings.llm_provider``.

    The application lifespan calls this once per process and closes the result
    at shutdown.

    :param settings: Settings selecting the implementation and supplying any Groq endpoint knobs.
    """

    match settings.llm_provider:
        case "stub":
            return StubLLMProvider()
        case "groq":
            return GroqLLMProvider(
                api_key=settings.groq_api_key,
                base_url=settings.groq_base_url,
                model=settings.groq_model,
                timeout_seconds=settings.llm_timeout_seconds,
                max_tokens=settings.llm_max_tokens,
                route_max_tokens=settings.llm_route_max_tokens,
                route_timeout_seconds=settings.llm_route_timeout_seconds,
            )
        case _ as unreachable:
            assert_never(unreachable)
