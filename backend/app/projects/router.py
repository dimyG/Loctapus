"""Project HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.models import Project
from app.projects.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from app.projects.service import (
    create_project,
    delete_project,
    get_project_for_user_with_role,
    get_project_visible_to_user,
    list_projects,
    list_public_projects,
    update_project,
)

router = APIRouter()


@router.post("/projects", status_code=201, response_model=ProjectOut)
def create(
    *,
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Create a project for ``body.team_id``, raising 404 when the user is not on that team."""

    project = create_project(db=db, user=user, team_id=body.team_id, name=body.name)
    if project is None:
        raise HTTPException(404, "team not found")
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_all(
    *,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Project]:
    """List projects shared with any of the user's teams."""

    return list_projects(db=db, user=user)


@router.get("/projects/public", response_model=list[ProjectOut])
def list_public(
    *,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Project]:
    """List every public project."""

    return list_public_projects(db=db)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_one(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Return a project visible to the user, raising 404 when it is missing or hidden."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update(
    *,
    project_id: UUID,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Update a project the user's team admins, raising 404 when the role is missing."""

    project = get_project_for_user_with_role(db=db, user=user, project_id=project_id, minimum_role="admin")
    if project is None:
        raise HTTPException(404, "project not found")
    return update_project(db=db, project=project, name=body.name, is_public=body.is_public)


@router.delete("/projects/{project_id}", status_code=204)
def delete(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a project the user's team admins, raising 404 when the role is missing."""

    project = get_project_for_user_with_role(db=db, user=user, project_id=project_id, minimum_role="admin")
    if project is None:
        raise HTTPException(404, "project not found")
    delete_project(db=db, project=project)
