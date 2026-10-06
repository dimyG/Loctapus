from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: UUID, settings: Settings) -> str:
    claims = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.jwt_access_token_ttl_hours),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> UUID:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return UUID(claims["sub"])
