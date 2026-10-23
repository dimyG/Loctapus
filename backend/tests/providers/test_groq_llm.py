"""Tests for the Groq LLM provider, run hermetically through MockTransport."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.providers.base import ChatMessage, LLMError, RouteDecision
from app.providers.groq_llm import GROQ_ERROR_COPY, GroqLLMProvider


def _provider(
    *,
    handler: Callable[[httpx.Request], httpx.Response],
    base_url: str = "https://groq.test",
    route_max_tokens: int = 128,
    route_timeout_seconds: float = 10.0,
) -> GroqLLMProvider:
    """Build a Groq provider around a hermetic MockTransport handler."""

    return GroqLLMProvider(
        api_key="gsk-test",
        base_url=base_url,
        model="openai/gpt-oss-20b",
        timeout_seconds=30.0,
        max_tokens=1024,
        route_max_tokens=route_max_tokens,
        route_timeout_seconds=route_timeout_seconds,
        transport=httpx.MockTransport(handler),
    )


def _router_reply(*, content: str) -> Callable[[httpx.Request], httpx.Response]:
    """Build one hermetic handler serving a canned router reply."""

    # httpx calls a MockTransport handler with one positional request, so the
    # closure cannot be keyword-only; it carries the same silencer as the rest.
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve the canned router reply."""

        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


def test_generate_returns_message_content() -> None:
    """A 200 completion returns its message content verbatim."""

    # httpx calls a MockTransport handler with one positional request, so the
    # handlers in this module cannot be keyword-only; each carries the silencer.
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one canned completion."""

        return httpx.Response(200, json={"choices": [{"message": {"content": "Rotate the key. [1]"}}]})

    provider = _provider(handler=handler)
    assert (
        provider.generate(system="be brief", messages=[ChatMessage(role="user", content="rotate the key")])
        == "Rotate the key. [1]"
    )


def test_generate_sends_model_key_and_messages() -> None:
    """One POST carries the endpoint path, the bearer key, and the ordered messages."""

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Capture the outgoing request and serve one canned completion."""

        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(handler=handler, base_url="https://groq.test/openai/v1")
    provider.generate(system="be brief", messages=[ChatMessage(role="user", content="rotate the key")])

    request = captured[0]
    assert request.url.path == "/openai/v1/chat/completions"
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
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_timeout_raises_llm_error() -> None:
    """A connect timeout surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Simulate the upstream never answering."""

        raise httpx.ConnectTimeout("connect timed out")

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_malformed_body_raises_llm_error() -> None:
    """A 200 with a non-JSON body surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one non-JSON body."""

        return httpx.Response(200, text="not json")

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_missing_choices_raises_llm_error() -> None:
    """A 200 body without choices surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one choices-free body."""

        return httpx.Response(200, json={})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_empty_choices_raises_llm_error() -> None:
    """A 200 body with an empty choices list surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one empty-choices body."""

        return httpx.Response(200, json={"choices": []})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


@pytest.mark.parametrize("content", ["", "   "])
def test_empty_content_raises_llm_error(*, content: str) -> None:
    """A 200 whose message content is blank surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one blank completion."""

        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.generate(system="s", messages=[ChatMessage(role="user", content="u")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_route_parses_valid_decision() -> None:
    """A strict-JSON router reply parses into one RouteDecision."""

    content = '{"route": "retrieve", "rewritten_query": "standalone q"}'
    provider = _provider(handler=_router_reply(content=content))
    decision = provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert decision == RouteDecision(route="retrieve", rewritten_query="standalone q")


def test_route_rejects_garbage_json() -> None:
    """A router reply that is not JSON surfaces as the user-safe LLMError."""

    provider = _provider(handler=_router_reply(content="route: retrieve"))
    with pytest.raises(LLMError) as excinfo:
        provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_route_rejects_unknown_route_literal() -> None:
    """A router reply naming an unknown route surfaces as the user-safe LLMError."""

    provider = _provider(handler=_router_reply(content='{"route": "teleport"}'))
    with pytest.raises(LLMError) as excinfo:
        provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_route_rejects_blank_rewritten_query() -> None:
    """A retrieval turn with a blank rewrite surfaces as the user-safe LLMError."""

    provider = _provider(handler=_router_reply(content='{"route": "retrieve", "rewritten_query": "  "}'))
    with pytest.raises(LLMError) as excinfo:
        provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert str(excinfo.value) == GROQ_ERROR_COPY


def test_route_accepts_missing_rewritten_query_on_reuse() -> None:
    """A reuse turn may omit the rewrite; the field is only required on retrieve."""

    provider = _provider(handler=_router_reply(content='{"route": "reuse"}'))
    decision = provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert decision == RouteDecision(route="reuse", rewritten_query=None)


def test_route_payload_carries_route_max_tokens_and_timeout() -> None:
    """The router POST carries its own max_tokens and per-call timeout."""

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Capture the router POST and serve one valid decision."""

        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"route": "direct"}'}}]})

    provider = _provider(handler=handler)
    provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])

    body = json.loads(captured[0].content)
    assert body["max_tokens"] == 128
    assert captured[0].extensions["timeout"]["read"] == 10.0


def test_route_maps_http_errors_to_llm_error() -> None:
    """A non-2xx router reply surfaces as the one fixed user-safe copy."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917
        """Serve one upstream failure."""

        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    provider = _provider(handler=handler)
    with pytest.raises(LLMError) as excinfo:
        provider.route(system="route the turn", messages=[ChatMessage(role="user", content="q")])
    assert str(excinfo.value) == GROQ_ERROR_COPY
