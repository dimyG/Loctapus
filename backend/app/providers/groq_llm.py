"""Groq LLM provider over the OpenAI-compatible chat completions endpoint."""

from typing import Final

import httpx

from app.providers.base import LLMError

GROQ_ERROR_COPY: Final = "The answer could not be generated right now. Please try again."


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
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Store the endpoint config and build one shared httpx client."""

        self._model = model
        self._max_tokens = max_tokens
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def generate(self, *, system: str, user: str) -> str:
        """Post one chat completion and return its message text."""

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self._max_tokens,
        }

        try:
            response = self._client.post("/chat/completions", json=payload)
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
