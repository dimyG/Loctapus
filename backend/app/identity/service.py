"""Business logic for registration, authentication, and token revocation."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
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


def register_user(*, db: Session, email: str, password: str) -> RegistrationResult:
    """Create a user with a default workspace, team, membership, and project in one transaction.

    :param db: Session the provisioning runs on; any failure rolls the whole thing back.
    :param email: Address to register, unique case-insensitively.
    :param password: Plaintext password, hashed before it is stored.
    """

    user = User(email=email, password_hash=hash_password(password=password))
    db.add(user)
    # Only the user insert can hit the email unique constraint, so only its flush maps to a
    # duplicate email; provisioning failures must surface as themselves.
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegisteredError(email) from None
    try:
        workspace = Workspace(name="Default", owner_user_id=user.id)
        db.add(workspace)
        db.flush()
        team = Team(workspace_id=workspace.id, name="Default")
        db.add(team)
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=user.id))
        db.flush()
        project = create_project_for_team(db=db, team=team, name="Default")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RegistrationResult(user=user, workspace=workspace, team=team, project=project)


def authenticate_user(*, db: Session, email: str, password: str) -> User | None:
    """Return the user when the password matches, otherwise None.

    :param db: Session the email lookup runs on.
    :param email: Address to look up.
    :param password: Plaintext password checked against the stored hash.
    """

    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(password=password, password_hash=user.password_hash):
        return None
    return user


def revoke_token(*, db: Session, jti: str, expires_at: datetime) -> None:
    """Record a token as revoked; repeated or concurrent calls with the same jti are a no-op.

    :param db: Session the insert commits through.
    :param jti: JWT ID claim identifying the token to revoke.
    :param expires_at: Expiry of the token, stored beside the jti.
    """

    # No conflict target is passed: any unique-constraint violation on revoked_tokens is
    # silently skipped, not only one on the jti primary key.
    statement = insert(RevokedToken).values(jti=jti, expires_at=expires_at).on_conflict_do_nothing()
    db.execute(statement)
    db.commit()


def is_token_revoked(*, db: Session, jti: str) -> bool:
    """Check whether ``jti`` has been revoked.

    :param db: Session the lookup runs on.
    :param jti: JWT ID claim to look up.
    """

    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None


def list_user_workspaces(*, db: Session, user: User) -> list[Workspace]:
    """List workspaces reachable through the user's team memberships.

    :param db: Session the join runs on.
    :param user: User whose memberships scope the listing.
    """

    return (
        db.query(Workspace)
        .join(Team, Team.workspace_id == Workspace.id)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(TeamMembership.user_id == user.id)
        .distinct()
        .all()
    )


def list_workspace_teams(*, db: Session, user: User, workspace_id: UUID) -> list[Team] | None:
    """List the user's teams in a workspace, or None when the user has no team there.

    :param db: Session the join runs on.
    :param user: User whose memberships scope the listing.
    :param workspace_id: Workspace whose teams are listed.
    """

    teams = (
        db.query(Team)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(Team.workspace_id == workspace_id, TeamMembership.user_id == user.id)
        .all()
    )
    return teams or None
