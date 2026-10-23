"""Tests for the stub LLM provider."""

from app.providers.base import ChatMessage, RouteDecision
from app.providers.stub_llm import STUB_ANSWER, StubLLMProvider


def test_stub_llm_is_deterministic() -> None:
    """Check that repeated calls with the same prompts return the fixed stub answer."""

    provider = StubLLMProvider()
    first = provider.generate(
        system="system prompt", messages=[ChatMessage(role="user", content="user prompt")]
    )
    second = provider.generate(
        system="system prompt", messages=[ChatMessage(role="user", content="user prompt")]
    )
    assert first == second == STUB_ANSWER
    assert "[1]" in first


def test_stub_llm_ignores_prompt_content() -> None:
    """Check that different prompts still produce the same output."""

    provider = StubLLMProvider()
    first = provider.generate(
        system="first system", messages=[ChatMessage(role="user", content="first user")]
    )
    second = provider.generate(
        system="second system", messages=[ChatMessage(role="user", content="second user")]
    )
    assert first == second == STUB_ANSWER


def test_stub_route_always_retrieves_with_raw_query() -> None:
    """The stub router keeps the offline path on today's retrieval behavior."""

    decision = StubLLMProvider().route(system="s", messages=[ChatMessage(role="user", content="q")])
    assert decision == RouteDecision(route="retrieve", rewritten_query=None)
