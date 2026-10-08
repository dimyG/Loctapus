"""Authentication and identity HTTP endpoints."""

from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import create_access_token, decode_access_token
from app.identity.dependencies import get_current_user
from app.identity.models import Team, User, Workspace
from app.identity.schemas import LoginRequest, RegisterRequest, TeamOut, WorkspaceOut
from app.identity.service import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    list_user_workspaces,
    list_workspace_teams,
    register_user,
    revoke_token,
)

router = APIRouter()


@router.post("/auth/register", status_code=201)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Register an account with a default workspace, team, and project, and return a bearer token."""

    try:
        result = register_user(db, body.email, body.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(409, "email already registered") from None
    return {
        "access_token": create_access_token(result.user.id, settings),
        "token_type": "bearer",
    }


@router.get("/users/me")
def users_me(
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return the id and email of the authenticated user."""

    return {
        "user_id": str(user.id),
        "email": user.email,
    }


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Workspace]:
    """List workspaces reachable through the user's team memberships."""

    return list_user_workspaces(db, user)


@router.get("/workspaces/{workspace_id}/teams", response_model=list[TeamOut])
def list_workspace_teams_view(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Team]:
    """List the user's teams inside ``workspace_id``, raising 404 when the user has none there."""

    teams = list_workspace_teams(db, user, workspace_id)
    if teams is None:
        raise HTTPException(404, "workspace not found")
    return teams


@router.post("/auth/login")
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Verify credentials and return a bearer token, raising 401 when they do not match."""

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
) -> Response:
    """Revoke the presented bearer token, raising 401 when it is invalid or expired."""

    try:
        claims = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid or expired token") from None
    revoke_token(db, claims.jti, claims.exp)
    return Response(status_code=204)
