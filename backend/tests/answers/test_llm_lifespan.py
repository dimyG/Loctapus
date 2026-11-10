"""Tests for the app lifespan's ownership of the LLM provider."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.main import app


class _ClosingLLMProvider:
    """LLM provider fake recording whether the lifespan closed it."""

    closed: bool = False

    async def aclose(self) -> None:
        """Record the shutdown close."""

        self.closed = True


def test_lifespan_owns_one_llm_provider(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that startup stores the provider on the app state and shutdown closes it.

    :param engine: Session-scoped engine bound to the migration-built test database.
    :param monkeypatch: Redirects the startup check and the provider factory.
    """

    fake = _ClosingLLMProvider()
    monkeypatch.setattr("app.main.run_startup_checks", _noop_startup_check)
    monkeypatch.setattr("app.main.get_llm_provider", _fake_provider_factory(fake=fake))
    with TestClient(app):
        assert app.state.llm_provider is fake
        assert fake.closed is False
    assert fake.closed is True


def test_failed_startup_check_builds_no_provider(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a refused boot builds no LLM provider, so nothing leaks.

    :param engine: Session-scoped engine bound to the migration-built test database.
    :param monkeypatch: Redirects the startup check and records factory calls.
    """

    built: list[object] = []
    monkeypatch.setattr("app.main.run_startup_checks", _failing_startup_check)
    monkeypatch.setattr("app.main.get_llm_provider", _recording_provider_factory(built=built))
    with pytest.raises(RuntimeError, match="boom"), TestClient(app):
        pass
    assert built == []


def _noop_startup_check(*, db: object, embedding_provider: object) -> None:
    """Succeed without checking anything.

    :param db: Session the check would have run on; unused.
    :param embedding_provider: Provider whose dimension the check would have verified; unused.
    """

    del db, embedding_provider


def _failing_startup_check(*, db: object, embedding_provider: object) -> None:
    """Raise the refusal the test asserts on.

    :param db: Session the check would have run on; unused.
    :param embedding_provider: Provider whose dimension the check would have verified; unused.
    """

    del db, embedding_provider
    raise RuntimeError("boom")


def _fake_provider_factory(*, fake: _ClosingLLMProvider) -> Callable[..., _ClosingLLMProvider]:
    """Return a factory returning the recording fake.

    :param fake: Fake provider the lifespan should store and close.
    """

    def factory(*, settings: object) -> _ClosingLLMProvider:
        """Return the fake provider.

        :param settings: Settings the factory would dispatch on; unused by this fake.
        """

        del settings
        return fake

    return factory


def _recording_provider_factory(*, built: list[object]) -> Callable[..., object]:
    """Return a factory recording every provider it is asked to build.

    :param built: List factory calls append their result to.
    """

    def factory(*, settings: object) -> object:
        """Return a placeholder provider and record the call.

        :param settings: Settings the factory would dispatch on; unused by this fake.
        """

        del settings
        provider = object()
        built.append(provider)
        return provider

    return factory
