"""Tests that the database rejects rows whose project differs from their parent's."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.models import Chunk, Document
from app.sources.models import SourceItem
from tests.factories import seed_project, seed_upload


def test_item_project_must_match_its_source(*, db_session: Session) -> None:
    """Check that a source item claimed by another project is rejected on flush."""

    project_a = seed_project(db=db_session, email="scope-item-a@example.com")
    project_b = seed_project(db=db_session, email="scope-item-b@example.com")
    seeded = seed_upload(db=db_session, project_id=project_a, filename="scoped.pdf", content=b"%PDF-a")

    db_session.add(
        SourceItem(
            source_id=seeded.source_id,
            project_id=project_b,
            external_id="impostor.pdf",
            filename="impostor.pdf",
            content_type="application/pdf",
            size_bytes=1,
            content_hash="impostor-hash",
            raw_object_key="raw/impostor/impostor/impostor/impostor.pdf",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_document_project_must_match_its_item(*, db_session: Session) -> None:
    """Check that a document claimed by another project is rejected on flush."""

    project_a = seed_project(db=db_session, email="scope-document-a@example.com")
    project_b = seed_project(db=db_session, email="scope-document-b@example.com")
    seeded = seed_upload(db=db_session, project_id=project_a, filename="scoped.pdf", content=b"%PDF-a")

    db_session.add(
        Document(
            source_item_id=seeded.source_item_id,
            project_id=project_b,
            content_hash="scoped-document-hash",
            raw_object_key=seeded.raw_object_key,
            normalized_content={"title": None, "elements": [], "metadata": {}},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_chunk_project_must_match_its_document(*, db_session: Session) -> None:
    """Check that a chunk claimed by another project is rejected on flush."""

    project_a = seed_project(db=db_session, email="scope-chunk-a@example.com")
    project_b = seed_project(db=db_session, email="scope-chunk-b@example.com")
    seeded = seed_upload(db=db_session, project_id=project_a, filename="chunked.pdf", content=b"%PDF-a")

    document = Document(
        source_item_id=seeded.source_item_id,
        project_id=project_a,
        content_hash="scoped-chunk-hash",
        raw_object_key=seeded.raw_object_key,
        normalized_content={"title": None, "elements": [], "metadata": {}},
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        Chunk(
            document_id=document.id,
            project_id=project_b,
            position=0,
            text="scoped text",
            heading_path=[],
            chunk_type="text",
            chunk_metadata={"filename": "chunked.pdf"},
            content_hash="chunk-hash",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
