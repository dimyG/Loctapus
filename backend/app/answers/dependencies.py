"""Request dependencies for the answer endpoint."""

from fastapi import Request

from app.providers.base import LLMProvider


async def get_app_llm_provider(*, request: Request) -> LLMProvider:
    """Return the one LLM provider the application lifespan built for this process.

    :param request: Request whose application state holds the provider.
    """

    provider: LLMProvider = request.app.state.llm_provider
    return provider
