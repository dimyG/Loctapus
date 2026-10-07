from sqlalchemy import inspect


def test_identity_tables_exist(engine):
    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    assert {"users", "workspaces", "teams", "team_memberships",
            "projects", "project_team_roles", "revoked_tokens"} <= names


def test_citext_email_case_insensitive(engine, db_session):
    from app.identity.models import User
    db_session.add(User(email="Case@Example.com", password_hash="x"))
    db_session.flush()
    found = db_session.query(User).filter(User.email == "case@example.com").one()
    assert found.email == "Case@Example.com"


def test_migration_is_head(settings):
    import subprocess
    out = subprocess.run(
        ["..\\.venv\\Scripts\\alembic.exe", "-c", "alembic.ini", "heads"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 0
    assert "0002" in out.stdout and "(head)" in out.stdout
