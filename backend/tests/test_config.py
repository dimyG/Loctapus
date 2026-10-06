from app.core.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://rag:rag@localhost:5432/rag"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_access_token_ttl_hours == 24


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    monkeypatch.setenv("RAG_JWT_SECRET", "abc")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:1/db"
    assert s.jwt_secret == "abc"
