import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import create_access_token, decode_access_token
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.identity.schemas import LoginRequest, RegisterRequest
from app.identity.service import (EmailAlreadyRegistered, authenticate_user,
                                  register_user, revoke_token)

router = APIRouter()


@router.post("/auth/register", status_code=201)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = register_user(db, body.email, body.password)
    except EmailAlreadyRegistered:
        raise HTTPException(409, "email already registered") from None
    return {
        "access_token": create_access_token(result.user.id, settings),
        "token_type": "bearer",
    }


@router.get("/users/me")
def users_me(
    user: User = Depends(get_current_user),
):
    return {
        "user_id": str(user.id),
        "email": user.email,
    }


@router.post("/auth/login")
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    user = authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(401, "invalid credentials")
    return {
        "access_token": create_access_token(user.id, settings),
        "token_type": "bearer",
    }


@router.post("/auth/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid or expired token") from None
    revoke_token(db, claims.jti, claims.exp)
    return Response(status_code=204)
