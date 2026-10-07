from app.identity import service as identity_service
from app.projects import service as project_service


def _user(db, email):
    result = identity_service.register_user(db, email, "password123")
    return result.user, result.team.id


def test_create_project_grants_personal_team_admin(db_session):
    user, team_id = _user(db_session, "owner@example.com")
    project = project_service.create_project(db_session, user, team_id, "kb1")
    fetched = project_service.get_project_for_user(db_session, user, project.id)
    assert fetched and fetched.name == "kb1"


def test_list_projects_scopes_to_user(db_session):
    alice, alice_team_id = _user(db_session, "alice@example.com")
    bob, bob_team_id = _user(db_session, "bob@example.com")
    project_service.create_project(db_session, alice, alice_team_id, "alice-kb")
    project_service.create_project(db_session, bob, bob_team_id, "bob-kb")
    assert sorted(p.name for p in project_service.list_projects(db_session, alice)) == [
        "Default", "alice-kb"]
    assert project_service.get_project_for_user(
        db_session, alice,
        project_service.list_projects(db_session, bob)[0].id) is None


def test_delete_project_removes_visibility(db_session):
    user, team_id = _user(db_session, "del@example.com")
    project = project_service.create_project(db_session, user, team_id, "gone")
    project_service.delete_project(db_session, project)
    assert project_service.get_project_for_user(db_session, user, project.id) is None


def test_get_project_for_user_with_role_requires_admin(db_session):
    from app.projects.models import ProjectTeamRole

    owner, owner_team_id = _user(db_session, "owner2@example.com")
    project = project_service.create_project(db_session, owner, owner_team_id, "shared")

    # second user whose team gets only a viewer role on the project
    viewer, viewer_team_id = _user(db_session, "viewer@example.com")
    db_session.add(
        ProjectTeamRole(project_id=project.id, team_id=viewer_team_id, role="viewer")
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
    user, team_id = _user(db_session, "dupe@example.com")
    a = project_service.create_project(db_session, user, team_id, "same")
    b = project_service.create_project(db_session, user, team_id, "same")
    assert a.id != b.id
    assert len(project_service.list_projects(db_session, user)) == 3


def test_get_project_visible_to_user_allows_public(db_session):
    owner, owner_team_id = _user(db_session, "vis-owner@example.com")
    stranger, _ = _user(db_session, "vis-stranger@example.com")
    project = project_service.create_project(db_session, owner, owner_team_id, "vis")
    assert project_service.get_project_visible_to_user(
        db_session, stranger, project.id) is None
    project.is_public = True
    db_session.commit()
    assert project_service.get_project_visible_to_user(
        db_session, stranger, project.id) is not None


def test_list_public_projects_only_returns_public(db_session):
    owner, owner_team_id = _user(db_session, "lp-owner@example.com")
    project_service.create_project(db_session, owner, owner_team_id, "lp-private")
    public_p = project_service.create_project(db_session, owner, owner_team_id, "lp-public")
    public_p.is_public = True
    db_session.commit()
    assert [x.id for x in project_service.list_public_projects(db_session)] == [public_p.id]


def test_update_project_name_and_visibility(db_session):
    owner, owner_team_id = _user(db_session, "up-owner@example.com")
    p = project_service.create_project(db_session, owner, owner_team_id, "before")
    updated = project_service.update_project(db_session, p, name="after", is_public=True)
    assert updated.name == "after" and updated.is_public is True
