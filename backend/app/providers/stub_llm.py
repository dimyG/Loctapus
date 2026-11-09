"""Stub LLM provider returning one fixed deterministic answer."""

from typing import Final

from app.providers.base import ChatMessage, RouteDecision

# The trailing [1] mimics a citation marker so the chat UI has a source chip
# to render in offline runs.
STUB_ANSWER: Final = "This is a stub answer grounded in the supplied context passages. [1]"


class StubLLMProvider:
    """Deterministic offline LLM for local development and tests."""

    def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Return the fixed stub answer, ignoring both prompts.

        :param system: System prompt, accepted for the interface and ignored.
        :param messages: Chat turns, accepted for the interface and ignored.
        """

        return STUB_ANSWER

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Route to retrieval with the raw question so offline runs keep today's behavior.

        :param system: Router prompt, accepted for the interface and ignored.
        :param messages: Chat turns, accepted for the interface and ignored.
        """

        return RouteDecision(route="retrieve", rewritten_query=None)
