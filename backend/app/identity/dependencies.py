"""FastAPI dependencies that authenticate the current request."""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import TokenClaims, decode_access_token
from app.identity.models import User
from app.identity.service import is_token_revoked


def get_token_claims(
    *,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    settings: Settings = Depends(get_settings),
) -> TokenClaims:
    """Return the verified claims of the bearer token, raising 401 when it is invalid.

    :param credentials: Bearer credentials extracted by the ``HTTPBearer`` scheme.
    :param settings: Settings supplying the expected secret and algorithm.
    """

    try:
        return decode_access_token(token=credentials.credentials, settings=settings)
    except jwt.InvalidTokenError:
        # Bad signature, expiry, and malformed claims all surface as InvalidTokenError,
        # so this one except clause maps every failure to the same 401.
        raise HTTPException(401, "invalid or expired token") from None


def get_current_user(
    *,
    claims: TokenClaims = Depends(get_token_claims),
    db: Session = Depends(get_db),
) -> User:
    """Return the user named by the bearer token, raising 401 when it is invalid or revoked.

    :param claims: Verified claims naming the user and carrying the jti.
    :param db: Session the revocation check and user lookup run on.
    """

    # Revoked and unknown-user tokens answer with the same detail as an invalid one, so
    # a caller cannot use the response to tell those states apart.
    if is_token_revoked(db=db, jti=claims.jti):
        raise HTTPException(401, "invalid or expired token")
    user = db.get(User, claims.user_id)
    if user is None:
        raise HTTPException(401, "invalid or expired token")
    return user
