"""Stub LLM provider returning one fixed deterministic answer."""

from typing import Final

STUB_ANSWER: Final = "This is a stub answer grounded in the supplied context passages. [1]"


class StubLLMProvider:
    """Deterministic offline LLM for local development and tests."""

    def generate(self, *, system: str, user: str) -> str:
        """Return the fixed stub answer, ignoring both prompts."""

        return STUB_ANSWER
