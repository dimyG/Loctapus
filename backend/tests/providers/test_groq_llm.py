"""Tests for the Groq LLM provider, run hermetically through MockTransport."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.providers.base import LLMError
from app.providers.groq_llm import GROQ_ERROR_COPY, GroqLLMProvider


def _provider(*, handler: Callable[[httpx.Request], httpx.Response]) -> GroqLLMProvider:
    """Build a Groq provider around a hermetic MockTransport handler."""

    return GroqLLMProvider(
        api_key="gsk-test",
        base_url="https://groq.test",
        model="openai/gpt-oss-20b",
        timeout_seconds=30.0,
        max_tokens=1024,
        transport=httpx.MockTransport(handler),
    )


def test_generate_returns_message_content() -> None:
    """A 200 completion returns its message content verbatim."""

    # httpx calls a MockTransport handler with one positional request, so the
    # handlers in this module cannot be keyword-only; each carries the silencer.
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one canned completion."""

        return httpx.Response(200, json={"choices": [{"message": {"content": "Rotate the key. [1]"}}]})

    provider = _provider(handler=handler)
    assert provider.generate(system="be brief", user="rotate the key") == "Rotate the key. [1]"


def test_generate_sends_model_key_and_messages() -> None:
    """One POST carries the endpoint path, the bearer key, and the ordered messages."""

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Capture the outgoing request and serve one canned completion."""

        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(handler=handler)
    provider.generate(system="be brief", user="rotate the key")

    request = captured[0]
    assert request.url.path == "/chat/completions"
    assert request.headers["Authorization"] == "Bearer gsk-test"
    body = json.loads(request.content)
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["max_tokens"] == 1024
    assert body["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "rotate the key"},
    ]


@pytest.mark.parametrize("status_code", [429, 500])
def test_non_2xx_raises_user_safe_llm_error(*, status_code: int) -> None:
    """A non-2xx response surfaces as the one fixed user-safe copy, never a raw HTTP error."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one upstream failure."""

        return httpx.Response(status_code, json={"error": {"message": "boom"}})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_timeout_raises_llm_error() -> None:
    """A connect timeout surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Simulate the upstream never answering."""

        raise httpx.ConnectTimeout("connect timed out")

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_malformed_body_raises_llm_error() -> None:
    """A 200 with a non-JSON body surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one non-JSON body."""

        return httpx.Response(200, text="not json")

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_missing_choices_raises_llm_error() -> None:
    """A 200 body without choices surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one choices-free body."""

        return httpx.Response(200, json={})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_empty_choices_raises_llm_error() -> None:
    """A 200 body with an empty choices list surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one empty-choices body."""

        return httpx.Response(200, json={"choices": []})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY


@pytest.mark.parametrize("content", ["", "   "])
def test_empty_content_raises_llm_error(*, content: str) -> None:
    """A 200 whose message content is blank surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one blank completion."""

        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", user="u")
    assert str(excinfo.value) == GROQ_ERROR_COPY
