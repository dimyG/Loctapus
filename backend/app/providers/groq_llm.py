"""Groq LLM provider over the OpenAI-compatible chat completions endpoint."""

import json
from typing import Final

import httpx

from app.providers.base import ChatMessage, LLMError, RouteDecision

GROQ_ERROR_COPY: Final = "The answer could not be generated right now. Please try again."

# The strict router contract: the reply's route must name one of these three paths.
_ROUTE_LITERALS: Final = ("direct", "reuse", "retrieve")


def _message_dicts(*, system: str, messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Render the system prompt plus the turns as OpenAI-style message dicts."""

    return [
        {"role": "system", "content": system},
        *({"role": message.role, "content": message.content} for message in messages),
    ]


class GroqLLMProvider:
    """Groq LLM client against the OpenAI-compatible chat/completions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        route_max_tokens: int,
        route_timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Store the endpoint config and build one shared httpx client."""

        self._model = model
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._route_max_tokens = route_max_tokens
        self._route_timeout_seconds = route_timeout_seconds
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def _complete(self, *, messages: list[dict[str, str]], max_tokens: int, timeout_seconds: float) -> str:
        """Post one chat completion with its own budget and timeout; return the message text."""

        payload = {"model": self._model, "messages": messages, "max_tokens": max_tokens}

        try:
            response = self._client.post("/chat/completions", json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, LookupError, TypeError) as error:
            # One user-safe copy for every transport, HTTP, and body-shape failure
            # (TimeoutException is an HTTPError subclass, LookupError covers both a
            # missing key and an empty list); the chained cause keeps the real
            # error visible in the server log.
            raise LLMError(GROQ_ERROR_COPY) from error

        if not isinstance(content, str) or not content.strip():
            # A blank or non-string completion is a failure, never an answer.
            raise LLMError(GROQ_ERROR_COPY)
        return content

    def generate(self, *, system: str, messages: list[ChatMessage]) -> str:
        """Post one chat completion and return its message text."""

        return self._complete(
            messages=_message_dicts(system=system, messages=messages),
            max_tokens=self._max_tokens,
            timeout_seconds=self._timeout_seconds,
        )

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Post one router completion and parse its strict JSON into a RouteDecision."""

        content = self._complete(
            messages=_message_dicts(system=system, messages=messages),
            max_tokens=self._route_max_tokens,
            timeout_seconds=self._route_timeout_seconds,
        )

        try:
            decision = json.loads(content)
        except ValueError as error:
            # A router reply that is not JSON is a failure the answer service falls back from.
            raise LLMError(GROQ_ERROR_COPY) from error
        if not isinstance(decision, dict) or decision.get("route") not in _ROUTE_LITERALS:
            raise LLMError(GROQ_ERROR_COPY)
        rewritten_query = decision.get("rewritten_query")
        if decision["route"] == "retrieve" and (
            not isinstance(rewritten_query, str) or not rewritten_query.strip()
        ):
            # A retrieval turn without a usable rewrite falls back to the raw question upstream.
            raise LLMError(GROQ_ERROR_COPY)
        return RouteDecision(
            route=decision["route"],
            rewritten_query=rewritten_query if isinstance(rewritten_query, str) else None,
        )
