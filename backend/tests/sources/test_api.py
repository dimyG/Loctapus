"""API tests for the upload and sources endpoints, against real Garage."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.models import Chunk, Document, IngestionRun
from app.ingestion.service import embed_document, ingest_source_item
from app.main import app
from app.outbox.events import SOURCE_ITEM_INGESTION_REQUESTED
from app.outbox.models import OutboxEvent
from app.projects.models import ProjectTeamRole
from app.providers import get_embedding_provider, get_parser
from app.sources.models import Source, SourceItem
from app.storage.service import StorageService, StorageUnavailableError, build_raw_object_key, get_storage
from tests.factories import seed_upload

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
PDF_CONTENT_TYPE = "application/pdf"


def _auth(*, client: TestClient, email: str) -> dict[str, str]:
    """Register an account and return its bearer headers."""

    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _default_team_id(*, client: TestClient, headers: dict[str, str]) -> str:
    """Return the account's default team id through the API."""

    ws = client.get("/workspaces", headers=headers).json()[0]
    return str(client.get(f"/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"])


def _create_project(*, client: TestClient, headers: dict[str, str], name: str) -> str:
    """Create a project through the API and return its id."""

    team_id = _default_team_id(client=client, headers=headers)
    created = client.post("/projects", json={"name": name, "team_id": team_id}, headers=headers)
    return str(created.json()["id"])


def _upload(
    *,
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    filename: str,
    content: bytes,
    content_type: str = PDF_CONTENT_TYPE,
) -> Response:
    """POST one multipart upload to the sources endpoint and return the response."""

    response: Response = client.post(
        f"/projects/{project_id}/sources",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )
    return response


def test_upload_creates_source_item_run_and_event(
    *, client: TestClient, db_session: Session, settings: Settings
) -> None:
    """Check the upload happy path: 201 SourceOut shape plus all four rows and the raw object."""

    headers = _auth(client=client, email="upload@example.com")
    project_id = _create_project(client=client, headers=headers, name="uploads")
    content = (FIXTURES_DIR / "tiny.pdf").read_bytes()

    r = _upload(client=client, headers=headers, project_id=project_id, filename="notes.pdf", content=content)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "project_id", "type", "status", "filename", "created_at"}
    assert body["type"] == "upload"
    assert body["status"] == "queued"
    assert body["filename"] == "notes.pdf"
    assert body["project_id"] == project_id

    source = db_session.query(Source).one()
    item = db_session.query(SourceItem).one()
    run = db_session.query(IngestionRun).one()
    event = db_session.query(OutboxEvent).one()

    assert source.id == UUID(body["id"])
    assert source.project_id == UUID(project_id)
    assert source.type == "upload"
    assert item.source_id == source.id
    assert item.external_id == "notes.pdf"
    assert item.filename == "notes.pdf"
    assert item.content_type == PDF_CONTENT_TYPE
    assert item.size_bytes == len(content)
    assert item.content_hash == hashlib.sha256(content).hexdigest()
    assert item.raw_object_key == build_raw_object_key(
        project_id=source.project_id,
        source_item_id=item.id,
        content_hash=item.content_hash,
        filename="notes.pdf",
    )
    assert run.source_item_id == item.id
    assert run.status == "queued"
    assert run.raw_object_key == item.raw_object_key
    assert run.content_hash == item.content_hash
    assert event.event_type == SOURCE_ITEM_INGESTION_REQUESTED
    assert event.aggregate_type == "source_item"
    assert event.aggregate_id == item.id
    assert event.published_at is None
    assert event.payload == {"ingestion_run_id": str(run.id)}
    assert StorageService(settings=settings).get_object(key=item.raw_object_key) == content


def test_storage_put_runs_with_no_open_transaction(
    *, client: TestClient, db_session: Session, settings: Settings
) -> None:
    """Check that no DB transaction is open on the request session across the storage PUT."""

    headers = _auth(client=client, email="put-txn@example.com")
    project_id = _create_project(client=client, headers=headers, name="put-txn")

    recorded: list[bool] = []

    class RecordingStorageService(StorageService):
        """Storage service that records the request session's transaction state during puts."""

        def put_object(self, *, key: str, content: bytes, content_type: str | None = None) -> None:
            """Record the transaction state, then store the bytes through the real client."""

            recorded.append(db_session.in_transaction())
            super().put_object(key=key, content=content, content_type=content_type)

    app.dependency_overrides[get_storage] = lambda: RecordingStorageService(settings=settings)

    r = _upload(
        client=client, headers=headers, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert r.status_code == 201
    assert recorded == [False]


def test_upload_storage_failure_returns_503(
    *, client: TestClient, db_session: Session, settings: Settings
) -> None:
    """Check that a storage failure during upload yields a 503 and leaves no rows."""

    headers = _auth(client=client, email="storage-failure@example.com")
    project_id = _create_project(client=client, headers=headers, name="storage-failure")

    class FailingStorageService(StorageService):
        """Storage service whose puts fail as if the backend were down."""

        def put_object(self, *, key: str, content: bytes, content_type: str | None = None) -> None:
            """Refuse the put with the unavailable error."""

            raise StorageUnavailableError("backend down")

    app.dependency_overrides[get_storage] = lambda: FailingStorageService(settings=settings)

    r = _upload(
        client=client, headers=headers, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "Could not store the file. Please try again."
    assert db_session.query(SourceItem).count() == 0


def test_upload_validates_extension_empty_and_size(*, client: TestClient) -> None:
    """Check the friendly 422s for a wrong extension, an empty file, and an oversized body."""

    headers = _auth(client=client, email="validate@example.com")
    project_id = _create_project(client=client, headers=headers, name="validation")

    txt = _upload(
        client=client,
        headers=headers,
        project_id=project_id,
        filename="notes.txt",
        content=b"text",
        content_type="text/plain",
    )
    assert txt.status_code == 422
    assert txt.json()["detail"] == "Only PDF and DOCX files are supported."

    empty = _upload(client=client, headers=headers, project_id=project_id, filename="empty.pdf", content=b"")
    assert empty.status_code == 422
    assert empty.json()["detail"] == "The file is empty."

    # The 26MB body must be rejected through UploadFile.size, before its bytes are read.
    oversized = _upload(
        client=client,
        headers=headers,
        project_id=project_id,
        filename="big.pdf",
        content=b"x" * (26 * 1024 * 1024),
    )
    assert oversized.status_code == 422
    assert oversized.json()["detail"] == "The file is too large. The maximum size is 25 MB."


def test_upload_filename_sanitized(*, client: TestClient, db_session: Session) -> None:
    """Check that the stored filename and the storage key use the sanitized basename."""

    headers = _auth(client=client, email="sanitize@example.com")
    project_id = _create_project(client=client, headers=headers, name="sanitize")

    r = _upload(
        client=client,
        headers=headers,
        project_id=project_id,
        filename="../evil/report.pdf",
        content=b"pdf bytes",
    )
    assert r.status_code == 201
    assert r.json()["filename"] == "report.pdf"

    source = db_session.query(Source).one()
    item = db_session.query(SourceItem).one()
    assert item.filename == "report.pdf"
    assert item.external_id == "report.pdf"
    assert item.raw_object_key == build_raw_object_key(
        project_id=source.project_id,
        source_item_id=item.id,
        content_hash=item.content_hash,
        filename="report.pdf",
    )

    empty_name = _upload(
        client=client, headers=headers, project_id=project_id, filename="/", content=b"pdf bytes"
    )
    assert empty_name.status_code == 422
    assert empty_name.json()["detail"] == "The file name is not supported."


def test_upload_requires_editor_role(*, client: TestClient, db_session: Session) -> None:
    """Check that a viewer-role member can list but not upload, and a stranger sees 404."""

    owner = _auth(client=client, email="owner@example.com")
    viewer = _auth(client=client, email="viewer@example.com")
    stranger = _auth(client=client, email="stranger@example.com")
    project_id = _create_project(client=client, headers=owner, name="roles")

    viewer_team_id = _default_team_id(client=client, headers=viewer)
    db_session.add(ProjectTeamRole(project_id=UUID(project_id), team_id=UUID(viewer_team_id), role="viewer"))
    db_session.flush()

    upload = _upload(
        client=client, headers=viewer, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert upload.status_code == 404
    assert upload.json() == {"detail": "project not found"}

    listed = client.get(f"/projects/{project_id}/sources", headers=viewer)
    assert listed.status_code == 200
    assert listed.json() == []

    stranger_upload = _upload(
        client=client, headers=stranger, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert stranger_upload.status_code == 404


def test_public_project_viewer_can_list_but_not_upload(*, client: TestClient) -> None:
    """Check that a stranger can list a public project's sources but cannot upload."""

    owner = _auth(client=client, email="public-owner@example.com")
    stranger = _auth(client=client, email="public-stranger@example.com")
    project_id = _create_project(client=client, headers=owner, name="public")
    assert client.patch(f"/projects/{project_id}", json={"is_public": True}, headers=owner).status_code == 200

    listed = client.get(f"/projects/{project_id}/sources", headers=stranger)
    assert listed.status_code == 200
    assert listed.json() == []

    upload = _upload(
        client=client, headers=stranger, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert upload.status_code == 404


def test_sources_list_derives_status_and_filename(*, client: TestClient, db_session: Session) -> None:
    """Check the list derives status and filename from each item's latest run, newest first."""

    headers = _auth(client=client, email="list@example.com")
    project_id = _create_project(client=client, headers=headers, name="listing")

    upload = _upload(
        client=client, headers=headers, project_id=project_id, filename="notes.pdf", content=b"pdf bytes"
    )
    assert upload.status_code == 201
    uploaded_source_id = upload.json()["id"]

    # Move the uploaded source's run forward so the listed status is derived, not just queued.
    run = db_session.query(IngestionRun).one()
    run.status = "processing"
    db_session.commit()

    # A second, explicitly older source with its own item and queued run.
    older = seed_upload(
        db=db_session, project_id=UUID(project_id), filename="older.pdf", content=b"older bytes"
    )
    older_source = db_session.get(Source, older.source_id)
    assert older_source is not None
    older_source.created_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    older_source_id = str(older.source_id)

    r = client.get(f"/projects/{project_id}/sources", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body] == [uploaded_source_id, older_source_id]
    assert body[0]["filename"] == "notes.pdf"
    assert body[0]["status"] == "processing"
    assert body[1]["filename"] == "older.pdf"
    assert body[1]["status"] == "queued"


def test_project_delete_cascades_fully_ingested_source(
    *, client: TestClient, db_session: Session, settings: Settings, storage: StorageService
) -> None:
    """Check that deleting a project with a fully ingested source removes every pipeline row."""

    headers = _auth(client=client, email="cascade@example.com")
    project_id = _create_project(client=client, headers=headers, name="cascade")
    content = (FIXTURES_DIR / "tiny.pdf").read_bytes()

    r = _upload(client=client, headers=headers, project_id=project_id, filename="tiny.pdf", content=content)
    assert r.status_code == 201

    run = db_session.query(IngestionRun).one()
    ingest_source_item(
        db=db_session,
        ingestion_run_id=run.id,
        storage=storage,
        parser=get_parser(settings=settings),
        settings=settings,
    )
    db_session.refresh(run)
    assert run.status == "indexing"
    document_id = run.document_id
    assert document_id is not None

    embed_document(
        db=db_session,
        document_id=document_id,
        ingestion_run_id=run.id,
        embedding_provider=get_embedding_provider(settings=settings),
        settings=settings,
    )
    db_session.refresh(run)
    assert run.status == "ready"
    assert db_session.query(Chunk).count() == 1

    assert client.delete(f"/projects/{project_id}", headers=headers).status_code == 204
    assert db_session.query(Source).count() == 0
    assert db_session.query(SourceItem).count() == 0
    assert db_session.query(Document).count() == 0
    assert db_session.query(Chunk).count() == 0
    assert db_session.query(IngestionRun).count() == 0
    # Outbox rows for deleted aggregates linger by design (no FK); later tasks no-op on them.
    assert db_session.query(OutboxEvent).count() == 2
