from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.schemas import ProjectCreate, ProjectOut
from app.projects.service import (create_project, delete_project,
                                  get_project_for_user,
                                  get_project_for_user_with_role,
                                  list_projects)

router = APIRouter()


@router.post("/projects", status_code=201, response_model=ProjectOut)
def create(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = create_project(db, user, body.team_id, body.name)
    if project is None:
        raise HTTPException(404, "team not found")
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_projects(db, user)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_one(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_for_user(db, user, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_for_user_with_role(db, user, project_id, roles=("admin",))
    if project is None:
        raise HTTPException(404, "project not found")
    delete_project(db, project)
