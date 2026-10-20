"""Tests for the stub LLM provider."""

from app.providers.stub_llm import STUB_ANSWER, StubLLMProvider


def test_stub_llm_is_deterministic() -> None:
    """Check that repeated calls with the same prompts return the fixed stub answer."""

    provider = StubLLMProvider()
    first = provider.generate(system="system prompt", user="user prompt")
    second = provider.generate(system="system prompt", user="user prompt")
    assert first == second == STUB_ANSWER
    assert "[1]" in first


def test_stub_llm_ignores_prompt_content() -> None:
    """Check that different prompts still produce the same output."""

    provider = StubLLMProvider()
    first = provider.generate(system="first system", user="first user")
    second = provider.generate(system="second system", user="second user")
    assert first == second == STUB_ANSWER
