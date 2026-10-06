from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.identity.schemas import LoginRequest, RegisterRequest
from app.identity.service import (EmailAlreadyRegistered, authenticate_user,
                                  register_user)

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
