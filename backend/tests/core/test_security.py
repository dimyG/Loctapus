"""Tests for password hashing and JWT access token handling."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from tests.helpers import SettingsForTests


def _settings() -> Settings:
    """Return settings with a known test secret."""

    return SettingsForTests(jwt_secret="test-secret")


def test_hash_roundtrip() -> None:
    """Check that a password hashes and verifies back."""

    h = hash_password(password="correct horse")
    assert h != "correct horse"
    assert verify_password(password="correct horse", password_hash=h)
    assert not verify_password(password="wrong", password_hash=h)


def test_token_roundtrip() -> None:
    """Check that a created token decodes to its user and a fresh jti."""

    uid = uuid.uuid4()
    token = create_access_token(user_id=uid, settings=_settings())
    claims = decode_access_token(token=token, settings=_settings())
    assert claims.user_id == uid and isinstance(claims.jti, str) and claims.jti


def test_jti_unique_across_tokens() -> None:
    """Check that every token gets a distinct jti."""

    uid = uuid.uuid4()
    a = decode_access_token(
        token=create_access_token(user_id=uid, settings=_settings()), settings=_settings()
    )
    b = decode_access_token(
        token=create_access_token(user_id=uid, settings=_settings()), settings=_settings()
    )
    assert a.jti != b.jti


def test_token_expiry_claim() -> None:
    """Check that the expiry claim honors the configured TTL."""

    token = create_access_token(user_id=uuid.uuid4(), settings=_settings())
    claims = jwt.decode(token, "test-secret", algorithms=["HS256"])
    exp = datetime.fromtimestamp(claims["exp"], tz=UTC)
    assert timedelta(hours=23) < exp - datetime.now(UTC) <= timedelta(hours=24)


def test_decode_rejects_garbage() -> None:
    """Check that undecodable input raises InvalidTokenError."""

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token="not-a-token", settings=_settings())


def test_decode_rejects_well_signed_token_without_sub() -> None:
    """Check that a signed token without sub is rejected."""

    token = jwt.encode({"exp": datetime.now(UTC) + timedelta(hours=1)}, "test-secret", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token=token, settings=_settings())


def test_decode_rejects_well_signed_token_with_bad_uuid_sub() -> None:
    """Check that a signed token with a non-UUID sub is rejected."""

    token = jwt.encode(
        {"sub": "not-a-uuid", "exp": datetime.now(UTC) + timedelta(hours=1)}, "test-secret", algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token=token, settings=_settings())
