"""Password hashing and JWT access token creation and verification."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

# One process-wide hasher: pwdlib hashes carry their own algorithm and parameters,
# so verification works without any matching configuration here.
_password_hash = PasswordHash.recommended()


def hash_password(*, password: str) -> str:
    """Hash ``password`` with the recommended password hashing algorithm.

    :param password: Plaintext password supplied by the caller.
    """

    return _password_hash.hash(password)


def verify_password(*, password: str, password_hash: str) -> bool:
    """Check ``password`` against ``password_hash``.

    :param password: Plaintext password to verify.
    :param password_hash: Stored hash previously produced by ``hash_password``.
    """

    return _password_hash.verify(password, password_hash)


@dataclass(frozen=True)
class TokenClaims:
    """Identity claims extracted from a signed access token."""

    user_id: UUID
    jti: str
    exp: datetime


def create_access_token(*, user_id: UUID, settings: Settings) -> str:
    """Return a signed access token for ``user_id`` that expires after the configured TTL.

    :param user_id: Identity the token stands for, carried as the ``sub`` claim.
    :param settings: Settings supplying the signing secret, algorithm, and TTL.
    """

    # The jti uniquely identifies the token for revocation; exp is fixed at issue
    # time, so a live token's lifetime cannot stretch past its configured TTL.
    claims = {
        "sub": str(user_id),
        "jti": str(uuid4()),
        "exp": datetime.now(UTC) + timedelta(hours=settings.jwt_access_token_ttl_hours),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(*, token: str, settings: Settings) -> TokenClaims:
    """Verify ``token`` and return its claims, raising ``jwt.InvalidTokenError`` when invalid.

    :param token: Signed token string produced by ``create_access_token``.
    :param settings: Settings supplying the expected secret and algorithm.
    """

    claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    try:
        return TokenClaims(
            user_id=UUID(claims["sub"]),
            jti=claims["jti"],
            exp=datetime.fromtimestamp(claims["exp"], tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        # Any malformed claim shape becomes InvalidTokenError, so callers only ever
        # handle the one failure type the API documents.
        raise jwt.InvalidTokenError("malformed token claims") from exc
