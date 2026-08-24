"""S3ObjectStore missing-key translation.

The object-store contract the routes depend on is the filesystem one:
``storage.fs.FilesystemStore.get`` raises KeyError for a missing object, and
both /images/{image_id} and /images/{image_id}/blob catch KeyError to return
404. Raw BucketStore lets botocore's ClientError escape, which becomes a 500.
"""

from __future__ import annotations

import pytest

pytest.importorskip("boto3")

import botocore.exceptions  # noqa: E402

from improv.objectstore import S3ObjectStore, build_s3_object_store  # noqa: E402


def _client_error(code: str) -> botocore.exceptions.ClientError:
    return botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": "nope"}}, "GetObject"
    )


class FakeClient:
    """Minimal stand-in for a boto3 S3 client."""

    def __init__(self, error: Exception | None = None, body: bytes = b"data") -> None:
        self._error = error
        self._body = body

    def get_object(self, Bucket, Key):  # noqa: N803 — boto3 kwarg casing
        if self._error is not None:
            raise self._error
        return {"Body": _Body(self._body)}

    def delete_object(self, Bucket, Key):  # noqa: N803
        if self._error is not None:
            raise self._error
        return {}


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


@pytest.mark.parametrize("code", ["404", "NoSuchKey"])
def test_get_translates_missing_key_to_keyerror(code):
    store = S3ObjectStore("images", client=FakeClient(_client_error(code)))
    with pytest.raises(KeyError):
        store.get("missing-image")


def test_get_returns_bytes_on_hit():
    store = S3ObjectStore("images", client=FakeClient(body=b"png-bytes"))
    assert store.get("some-image") == b"png-bytes"


def test_get_propagates_other_client_errors():
    """AccessDenied must not masquerade as a 404."""
    store = S3ObjectStore("images", client=FakeClient(_client_error("AccessDenied")))
    with pytest.raises(botocore.exceptions.ClientError):
        store.get("some-image")


@pytest.mark.parametrize("code", ["404", "NoSuchKey"])
def test_delete_translates_missing_key_to_keyerror(code):
    store = S3ObjectStore("images", client=FakeClient(_client_error(code)))
    with pytest.raises(KeyError):
        store.delete("missing-image")


def test_build_s3_object_store_uses_endpoint_and_bucket():
    store = build_s3_object_store(
        bucket="images",
        endpoint_url="https://vast-s3.example",
        access_key="ak",
        secret_key="sk",
    )
    assert isinstance(store, S3ObjectStore)
    assert store.bucket_name == "images"
    assert store.s3_client.meta.endpoint_url == "https://vast-s3.example"
