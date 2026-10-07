import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (create_access_token, decode_access_token,
                               hash_password, verify_password)


def _settings():
    return Settings(_env_file=None, jwt_secret="test-secret")


def test_hash_roundtrip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    uid = uuid.uuid4()
    token = create_access_token(uid, _settings())
    claims = decode_access_token(token, _settings())
    assert claims.user_id == uid and isinstance(claims.jti, str) and claims.jti


def test_jti_unique_across_tokens():
    uid = uuid.uuid4()
    a = decode_access_token(create_access_token(uid, _settings()), _settings())
    b = decode_access_token(create_access_token(uid, _settings()), _settings())
    assert a.jti != b.jti


def test_token_expiry_claim():
    token = create_access_token(uuid.uuid4(), _settings())
    claims = jwt.decode(token, "test-secret", algorithms=["HS256"])
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert timedelta(hours=23) < exp - datetime.now(timezone.utc) <= timedelta(hours=24)


def test_decode_rejects_garbage():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token", _settings())


def test_decode_rejects_well_signed_token_without_sub():
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, _settings())


def test_decode_rejects_well_signed_token_with_bad_uuid_sub():
    token = jwt.encode(
        {"sub": "not-a-uuid",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, _settings())
