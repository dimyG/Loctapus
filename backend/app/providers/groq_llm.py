"""Groq LLM provider over the OpenAI-compatible chat completions endpoint."""

import json
from typing import Final

import httpx

from app.providers.base import ChatMessage, LLMError, RouteDecision

# The only error text this provider raises; keep it user-safe because the
# answers router can send it to the API client as the 502 detail.
GROQ_ERROR_COPY: Final = "The answer could not be generated right now. Please try again."

# The strict router contract: the reply's route must name one of these three paths.
_ROUTE_LITERALS: Final = ("direct", "reuse", "retrieve")


def _message_dicts(*, system: str, messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Render the system prompt plus the turns as OpenAI-style message dicts.

    :param system: System prompt sent as the first message.
    :param messages: Chat turns in send order, after the system prompt.
    """

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
        """Store the endpoint config and build one shared httpx client.

        One client serves every generate and route call, and the application
        lifespan closes it at shutdown, so connections pool for the whole
        app process.

        :param api_key: Groq API key sent as the bearer token.
        :param base_url: OpenAI-compatible base URL; ``/chat/completions`` is appended.
        :param model: Model name sent in every request body.
        :param timeout_seconds: Default timeout for generate calls.
        :param max_tokens: Completion budget for generate calls.
        :param route_max_tokens: Smaller completion budget for router calls.
        :param route_timeout_seconds: Shorter timeout for router calls.
        :param transport: Optional httpx transport; tests use it to fake the wire.
        """

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
        """Post one chat completion with its own budget and timeout; return the message text.

        :param messages: OpenAI-style message dicts, system prompt first.
        :param max_tokens: Completion budget sent in the request body.
        :param timeout_seconds: Per-call timeout overriding the client default.
        """

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
        """Post one chat completion and return its message text.

        :param system: System prompt steering the completion.
        :param messages: Prior turns in send order, oldest first.
        """

        return self._complete(
            messages=_message_dicts(system=system, messages=messages),
            max_tokens=self._max_tokens,
            timeout_seconds=self._timeout_seconds,
        )

    def route(self, *, system: str, messages: list[ChatMessage]) -> RouteDecision:
        """Post one router completion and parse its strict JSON into a RouteDecision.

        :param system: Router prompt requiring the strict JSON shape.
        :param messages: Prior turns in send order, oldest first.
        """

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
            # A retrieve turn without a usable rewrite is a contract failure;
            # the answer service catches it and falls back to the raw question.
            raise LLMError(GROQ_ERROR_COPY)
        return RouteDecision(
            route=decision["route"],
            rewritten_query=rewritten_query if isinstance(rewritten_query, str) else None,
        )

    async def aclose(self) -> None:
        """Close the shared client, ending its pooled connections.

        :param: None.
        """

        self._client.close()
