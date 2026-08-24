"""S3-backed object store for image bytes and binary products.

``storage.s3.BucketStore`` takes an injected client and does no endpoint or
credential handling of its own, so this module owns constructing a boto3 client
against an S3-compatible endpoint (VAST S3, MinIO) and normalizing its
missing-key behaviour.

Imports ``boto3`` at module load, so import this lazily — only when an S3
object store is actually configured. ``boto3`` arrives via the
``amplify-storage-utils[s3]`` extra and is absent from a base install.
"""

from __future__ import annotations

import boto3
import botocore.exceptions
from storage.s3 import BucketStore

# botocore reports a missing object under either code depending on whether the
# call was a HEAD or a GET.
_MISSING_KEY_CODES = frozenset({"404", "NoSuchKey"})


class S3ObjectStore(BucketStore):
    """BucketStore that raises ``KeyError`` for a missing key.

    The object-store contract the routes rely on is the filesystem one:
    ``storage.fs.FilesystemStore.get`` translates a missing file into
    ``KeyError``, and both ``/images/{image_id}`` and ``/images/{image_id}/blob``
    catch ``KeyError`` to return 404. Raw ``BucketStore`` lets botocore's
    ``ClientError`` escape, which would surface as a 500 instead.
    """

    def get(self, key):
        try:
            return super().get(key)
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING_KEY_CODES:
                raise KeyError(key) from exc
            raise

    def delete(self, key):
        try:
            return super().delete(key)
        except botocore.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING_KEY_CODES:
                raise KeyError(key) from exc
            raise


def build_s3_object_store(
    bucket: str,
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    *,
    verify: bool | str = True,
) -> S3ObjectStore:
    """Build an S3ObjectStore against an S3-compatible endpoint.

    Args:
        bucket: Bucket holding image bytes and blobs.
        endpoint_url: Full URL *with scheme*, e.g. ``https://vast-s3.whoi.edu``.
            Note this differs from the columnar store's ``IMPROV_S3_ENDPOINT``,
            which DuckDB and PyArrow want as a bare ``host:port``.
        access_key: S3 access key ID.
        secret_key: S3 secret access key.
        verify: TLS verification — ``True``, ``False``, or a path to a CA
            bundle for an internally-signed endpoint.
    """
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        verify=verify,
    )
    return S3ObjectStore(bucket, client=client)
