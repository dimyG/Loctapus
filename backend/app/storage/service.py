"""Garage-backed object storage and the raw object key convention."""

from functools import lru_cache
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings


class StorageError(Exception):
    """Base for every object storage failure."""


class ObjectNotFoundError(StorageError):
    """Raised when the requested object does not exist in the bucket."""


class StorageUnavailableError(StorageError):
    """Raised when the object storage backend cannot serve a request."""


def build_raw_object_key(*, project_id: UUID, source_item_id: UUID, content_hash: str, filename: str) -> str:
    """Return the storage key under which a source item's raw bytes live."""

    return f"raw/{project_id}/{source_item_id}/{content_hash}/{filename}"


class StorageService:
    """S3 client bound to the configured Garage bucket."""

    def __init__(self, *, settings: Settings) -> None:
        """Create the boto3 client from the settings' S3 block, with path-style addressing."""

        self._bucket = settings.s3_bucket
        # A dedicated session keeps this client independent of boto3's shared default
        # session, and the timeouts plus standard retries bound every request this
        # process makes against Garage.
        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            # Garage is addressed as {endpoint}/{bucket}/{key}, not DNS-style virtual hosts.
            config=Config(
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=30,
                retries={"mode": "standard", "max_attempts": 3},
            ),
        )

    def put_object(self, *, key: str, content: bytes, content_type: str | None = None) -> None:
        """Store ``content`` under ``key``, optionally labelling it with a content type."""

        try:
            if content_type is None:
                self._client.put_object(Bucket=self._bucket, Key=key, Body=content)
            else:
                self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError(f"put failed for key {key!r}: {exc}") from exc

    def get_object(self, *, key: str) -> bytes:
        """Return the bytes stored under ``key``, raising ObjectNotFoundError when absent."""

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            # Garage reports a missing object as NoSuchKey or a bare 404; every other
            # client error means the backend served a failure instead.
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise ObjectNotFoundError(f"no object under key {key!r}") from exc
            raise StorageUnavailableError(f"get failed for key {key!r}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError(f"get failed for key {key!r}: {exc}") from exc

    def delete_object(self, *, key: str) -> None:
        """Delete the object under ``key``; S3 deletes are idempotent, so a missing key is a no-op."""

        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError(f"delete failed for key {key!r}: {exc}") from exc


@lru_cache
def get_storage() -> StorageService:
    """Return the process-wide storage service, built from the current settings.

    Both the FastAPI dependency and the worker accessor resolve through this one
    cache, so each process owns a single configured client.
    """

    return StorageService(settings=get_settings())
