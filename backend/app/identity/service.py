from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.identity.models import Team, TeamMembership, User, Workspace


class EmailAlreadyRegistered(Exception):
    pass


@dataclass
class RegistrationResult:
    user: User
    workspace: Workspace
    team: Team


def register_user(db: Session, email: str, password: str) -> RegistrationResult:
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
        workspace = Workspace(name="Personal", owner_user_id=user.id)
        db.add(workspace)
        db.flush()
        team = Team(workspace_id=workspace.id, name="Personal")
        db.add(team)
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered(email) from None
    return RegistrationResult(user=user, workspace=workspace, team=team)


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
