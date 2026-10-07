from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.identity.models import (RevokedToken, Team, TeamMembership, User,
                                 Workspace)
from app.projects.models import Project


class EmailAlreadyRegistered(Exception):
    pass


@dataclass
class RegistrationResult:
    user: User
    workspace: Workspace
    team: Team
    project: Project


def register_user(db: Session, email: str, password: str) -> RegistrationResult:
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
        workspace = Workspace(name="Default", owner_user_id=user.id)
        db.add(workspace)
        db.flush()
        team = Team(workspace_id=workspace.id, name="Default")
        db.add(team)
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=user.id))
        db.flush()
        # Deferred import avoids a module-load cycle: app.projects.service
        # still imports get_personal_context from this module until Task 5.
        from app.projects.service import create_project_for_team
        project = create_project_for_team(db, team, "Default")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered(email) from None
    except Exception:
        db.rollback()
        raise
    return RegistrationResult(user=user, workspace=workspace, team=team,
                              project=project)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_personal_context(db: Session, user_id: UUID) -> tuple[Workspace, Team]:
    workspace = (
        db.query(Workspace)
        .filter(Workspace.owner_user_id == user_id)
        .one()
    )
    team = (
        db.query(Team)
        .filter(Team.workspace_id == workspace.id)
        .one()
    )
    return workspace, team


def revoke_token(db: Session, jti: str, expires_at: datetime) -> None:
    if not is_token_revoked(db, jti):
        db.add(RevokedToken(jti=jti, expires_at=expires_at))
        db.commit()


def is_token_revoked(db: Session, jti: str) -> bool:
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None
