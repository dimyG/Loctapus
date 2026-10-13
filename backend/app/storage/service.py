"""Garage-backed object storage and the raw object key convention."""

from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings


class StorageUnavailableError(Exception):
    """Raised when the object storage backend cannot serve a request."""


def build_raw_object_key(*, project_id: UUID, source_item_id: UUID, content_hash: str, filename: str) -> str:
    """Return the storage key under which a source item's raw bytes live."""

    return f"raw/{project_id}/{source_item_id}/{content_hash}/{filename}"


class StorageService:
    """S3 client bound to the configured Garage bucket."""

    def __init__(self, *, settings: Settings) -> None:
        """Create the boto3 client from the settings' S3 block, with path-style addressing."""

        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            # Garage is addressed as {endpoint}/{bucket}/{key}, not DNS-style virtual hosts.
            config=Config(s3={"addressing_style": "path"}),
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
        """Return the bytes stored under ``key``."""

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except (ClientError, BotoCoreError) as exc:
            raise StorageUnavailableError(f"get failed for key {key!r}: {exc}") from exc
