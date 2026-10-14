"""Tests for the stub embedding provider."""

import pytest
from pydantic import ValidationError

from app.providers.stub_embeddings import STUB_EMBEDDING_DIM, StubEmbeddingProvider
from tests.helpers import SettingsForTests


def _provider() -> StubEmbeddingProvider:
    """Return a fresh stub embedding provider."""

    return StubEmbeddingProvider()


def test_embedding_is_deterministic() -> None:
    """Check that identical texts embed identically and different texts differ."""

    provider = _provider()
    first = provider.embed_documents(texts=["hello world"])
    second = provider.embed_documents(texts=["hello world"])
    assert first == second
    assert provider.embed_query(text="hello world") == first[0]
    assert provider.embed_documents(texts=["goodbye world"]) != first


def test_dimension_matches_constant() -> None:
    """Check that vectors and the provider dimension match STUB_EMBEDDING_DIM."""

    provider = _provider()
    vector = provider.embed_documents(texts=["some text"])[0]
    assert len(vector) == STUB_EMBEDDING_DIM == 384
    assert provider.dimension == 384


def test_l2_normalized() -> None:
    """Check that non-empty texts produce unit-length vectors."""

    provider = _provider()
    for text in ["hello", "hello HELLO world", "a b c d e"]:
        vector = provider.embed_query(text=text)
        assert abs(sum(value * value for value in vector) - 1.0) < 1e-6


def test_empty_text_yields_zero_vector() -> None:
    """Check that empty input yields the zero vector."""

    provider = _provider()
    assert provider.embed_query(text="") == [0.0] * STUB_EMBEDDING_DIM
    assert provider.embed_documents(texts=["", "   "]) == [[0.0] * STUB_EMBEDDING_DIM] * 2


def test_unknown_embedding_provider_setting_is_rejected() -> None:
    """An unknown embedding provider string is rejected at settings construction.

    The invalid value goes through ``model_validate`` because the typed constructor
    signature itself refuses it: rejection at construction is the feature.
    """

    with pytest.raises(ValidationError, match="stub"):
        SettingsForTests.model_validate({"embedding_provider": "nope"})
