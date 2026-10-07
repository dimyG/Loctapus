from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    jti: str
    exp: datetime


def create_access_token(user_id: UUID, settings: Settings) -> str:
    claims = {
        "sub": str(user_id),
        "jti": str(uuid4()),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.jwt_access_token_ttl_hours),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    try:
        return TokenClaims(
            user_id=UUID(claims["sub"]),
            jti=claims["jti"],
            exp=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )
    except (KeyError, ValueError) as exc:
        raise jwt.InvalidTokenError("malformed token claims") from exc
