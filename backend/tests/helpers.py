"""Shared test helpers."""

from pydantic_settings import SettingsConfigDict

from app.core.config import Settings


class SettingsForTests(Settings):
    """Settings subclass for tests, identical to Settings but it never reads a .env file."""

    model_config = SettingsConfigDict(env_file=None)
