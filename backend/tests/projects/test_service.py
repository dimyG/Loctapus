from app.identity import service as identity_service
from app.projects import service as project_service


def _user(db, email):
    return identity_service.register_user(db, email, "password123").user


def test_create_project_grants_personal_team_admin(db_session):
    user = _user(db_session, "owner@example.com")
    project = project_service.create_project(db_session, user, "kb1")
    fetched = project_service.get_project_for_user(db_session, user, project.id)
    assert fetched and fetched.name == "kb1"


def test_list_projects_scopes_to_user(db_session):
    alice = _user(db_session, "alice@example.com")
    bob = _user(db_session, "bob@example.com")
    project_service.create_project(db_session, alice, "alice-kb")
    project_service.create_project(db_session, bob, "bob-kb")
    assert [p.name for p in project_service.list_projects(db_session, alice)] == ["alice-kb"]
    assert project_service.get_project_for_user(
        db_session, alice,
        project_service.list_projects(db_session, bob)[0].id) is None


def test_delete_project_removes_visibility(db_session):
    user = _user(db_session, "del@example.com")
    project = project_service.create_project(db_session, user, "gone")
    project_service.delete_project(db_session, project)
    assert project_service.get_project_for_user(db_session, user, project.id) is None


def test_get_project_for_user_with_role_requires_admin(db_session):
    import uuid

    from app.identity.models import Team, TeamMembership, Workspace
    from app.projects.models import Project, ProjectTeamRole

    owner = _user(db_session, "owner2@example.com")
    project = project_service.create_project(db_session, owner, "shared")

    # second user whose personal team gets only a viewer role on the project
    viewer = _user(db_session, "viewer@example.com")
    _, viewer_team = identity_service.get_personal_context(db_session, viewer.id)
    db_session.add(
        ProjectTeamRole(project_id=project.id, team_id=viewer_team.id, role="viewer")
    )
    db_session.flush()

    admin_view = project_service.get_project_for_user_with_role(
        db_session, owner, project.id, roles=("admin",)
    )
    viewer_view = project_service.get_project_for_user_with_role(
        db_session, viewer, project.id, roles=("admin",)
    )
    assert admin_view is not None
    assert viewer_view is None


def test_duplicate_project_name_allowed(db_session):
    user = _user(db_session, "dupe@example.com")
    a = project_service.create_project(db_session, user, "same")
    b = project_service.create_project(db_session, user, "same")
    assert a.id != b.id
    assert len(project_service.list_projects(db_session, user)) == 2
