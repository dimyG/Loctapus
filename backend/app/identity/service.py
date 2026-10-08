"""Business logic for registration, authentication, and token revocation."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.identity.models import RevokedToken, Team, TeamMembership, User, Workspace
from app.projects.models import Project
from app.projects.service import create_project_for_team


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that already exists."""


@dataclass
class RegistrationResult:
    """Objects provisioned for a newly registered user."""

    user: User
    workspace: Workspace
    team: Team
    project: Project


def register_user(db: Session, email: str, password: str) -> RegistrationResult:
    """Create a user with a default workspace, team, membership, and project in one transaction."""

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
        project = create_project_for_team(db, team, "Default")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegisteredError(email) from None
    except Exception:
        db.rollback()
        raise
    return RegistrationResult(user=user, workspace=workspace, team=team, project=project)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user when the password matches, otherwise None."""

    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def revoke_token(db: Session, jti: str, expires_at: datetime) -> None:
    """Record a token as revoked; repeated calls with the same jti are a no-op."""

    if not is_token_revoked(db, jti):
        db.add(RevokedToken(jti=jti, expires_at=expires_at))
        db.commit()


def is_token_revoked(db: Session, jti: str) -> bool:
    """Check whether ``jti`` has been revoked."""

    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None


def list_user_workspaces(db: Session, user: User) -> list[Workspace]:
    """List workspaces reachable through the user's team memberships."""

    return (
        db.query(Workspace)
        .join(Team, Team.workspace_id == Workspace.id)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(TeamMembership.user_id == user.id)
        .distinct()
        .all()
    )


def list_workspace_teams(db: Session, user: User, workspace_id: UUID) -> list[Team] | None:
    """List the user's teams in a workspace, or None when the user has no team there."""

    teams = (
        db.query(Team)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(Team.workspace_id == workspace_id, TeamMembership.user_id == user.id)
        .all()
    )
    return teams or None
