"""Tests for the Garage storage service and the raw object key convention."""

from uuid import UUID, uuid4

import pytest

from app.storage import (
    ObjectNotFoundError,
    StorageService,
    StorageUnavailableError,
    build_raw_object_key,
    get_storage,
)
from tests.helpers import SettingsForTests

PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
SOURCE_ITEM_ID = UUID("22222222-2222-2222-2222-222222222222")
CONTENT_HASH = "abc123"


def test_object_key_format() -> None:
    """Check that keys follow raw/{project_id}/{source_item_id}/{content_hash}/{filename}."""

    key = build_raw_object_key(
        project_id=PROJECT_ID,
        source_item_id=SOURCE_ITEM_ID,
        content_hash=CONTENT_HASH,
        filename="a.pdf",
    )
    assert key == f"raw/{PROJECT_ID}/{SOURCE_ITEM_ID}/{CONTENT_HASH}/a.pdf"


def _service() -> StorageService:
    """Return a service pointed at the compose Garage with the dev bucket."""

    return StorageService(settings=SettingsForTests())


def test_put_get_roundtrip() -> None:
    """Check that bytes put under a UUID-carrying key come back unchanged."""

    service = _service()
    key = build_raw_object_key(
        project_id=PROJECT_ID,
        source_item_id=uuid4(),
        content_hash=CONTENT_HASH,
        filename="roundtrip.bin",
    )
    # Both content-type branches are exercised; the second put overwrites the first.
    service.put_object(key=key, content=b"hello garage", content_type="application/octet-stream")
    assert service.get_object(key=key) == b"hello garage"
    service.put_object(key=key, content=b"no content type")
    assert service.get_object(key=key) == b"no content type"


def test_get_missing_key_raises_object_not_found() -> None:
    """Check that reading an absent key raises ObjectNotFoundError, not unavailable."""

    service = _service()
    key = build_raw_object_key(
        project_id=uuid4(),
        source_item_id=uuid4(),
        content_hash=CONTENT_HASH,
        filename="missing.bin",
    )
    with pytest.raises(ObjectNotFoundError):
        service.get_object(key=key)


def test_delete_object_removes_the_stored_bytes() -> None:
    """Check that a deleted object no longer reads back."""

    service = _service()
    key = build_raw_object_key(
        project_id=PROJECT_ID,
        source_item_id=uuid4(),
        content_hash=CONTENT_HASH,
        filename="delete-me.bin",
    )
    service.put_object(key=key, content=b"goodbye")
    service.delete_object(key=key)
    with pytest.raises(ObjectNotFoundError):
        service.get_object(key=key)


def test_delete_missing_key_is_a_noop() -> None:
    """Check that deleting an absent key does not raise, so partial state stays deletable."""

    service = _service()
    key = build_raw_object_key(
        project_id=uuid4(),
        source_item_id=uuid4(),
        content_hash=CONTENT_HASH,
        filename="absent.bin",
    )
    service.delete_object(key=key)


def test_unreachable_endpoint_raises_unavailable() -> None:
    """Check that an unreachable storage endpoint raises StorageUnavailableError."""

    service = StorageService(settings=SettingsForTests(s3_endpoint="http://127.0.0.1:1"))
    with pytest.raises(StorageUnavailableError):
        service.get_object(key="raw/nowhere/nowhere/none/missing.bin")


def test_get_storage_returns_one_cached_service() -> None:
    """Check that get_storage hands out one cached service per process."""

    first = get_storage()
    assert get_storage() is first
