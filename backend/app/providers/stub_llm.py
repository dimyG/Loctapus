"""Stub LLM provider returning one fixed deterministic answer."""

from typing import Final

from app.providers.base import ChatMessage, RouteDecision

STUB_ANSWER: Final = "This is a stub answer grounded in the supplied context passages. [1]"


class StubLLMProvider:
    """Deterministic offline LLM for local development and tests."""

    def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Return the fixed stub answer, ignoring both prompts."""

        return STUB_ANSWER

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Route to retrieval with the raw question so offline runs keep today's behavior."""

        return RouteDecision(route="retrieve", rewritten_query=None)
