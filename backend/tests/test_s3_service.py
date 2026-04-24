"""
Pytest test suite for app/services/s3_service.py

Covers:
- _client           : creates boto3 S3 client using settings credentials
- upload_file       : key format, correct bucket + args, returns key,
                      ClientError → StorageError, BotoCoreError → StorageError
- delete_file       : correct bucket + key, returns None,
                      ClientError → StorageError, BotoCoreError → StorageError
- get_presigned_url : correct operation + params + expiry, returns URL string,
                      ClientError → StorageError, BotoCoreError → StorageError
- download_file_bytes : reads Body, returns bytes,
                        ClientError → StorageError, BotoCoreError → StorageError

No real AWS credentials or network calls are made — boto3 client is always
mocked at the _client() level.

Settings are stubbed via tests/conftest.py.
"""

import io
import re
import uuid
import pytest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, BotoCoreError

from app.core.exceptions import StorageError
from app.services.s3_service import (
    _client,
    upload_file,
    delete_file,
    get_presigned_url,
    download_file_bytes,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _client_error(code: str = "InternalError", op: str = "TestOp") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "test error"}}, op)


class _FakeBotoCoreError(BotoCoreError):
    """Concrete subclass — BotoCoreError itself cannot be instantiated directly."""
    fmt = "fake botocore error"


def _mock_client(side_effect=None, **method_returns):
    """
    Return a mock that replaces _client().
    method_returns maps method names → return values.
    side_effect, if given, applies to every method call.
    """
    mock = MagicMock()
    for method, retval in method_returns.items():
        getattr(mock, method).return_value = retval
    if side_effect is not None:
        for method in ("upload_fileobj", "delete_object",
                       "generate_presigned_url", "get_object"):
            getattr(mock, method).side_effect = side_effect
    return mock


# Convenience: patch _client() to return a controlled mock
def _patch_client(mock):
    return patch("app.services.s3_service._client", return_value=mock)


# ===========================================================================
# _client
# ===========================================================================

class TestClient:
    def test_returns_boto3_s3_client(self):
        import boto3
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            client = _client()
        mock_boto.assert_called_once()
        call_args = mock_boto.call_args
        assert call_args.args[0] == "s3"

    def test_uses_region_from_settings(self):
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            _client()
        kwargs = mock_boto.call_args.kwargs
        assert kwargs["region_name"] == "eu-central-1"

    def test_uses_access_key_from_settings(self):
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            _client()
        kwargs = mock_boto.call_args.kwargs
        assert kwargs["aws_access_key_id"] == "test-key-id"

    def test_uses_secret_key_from_settings(self):
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            _client()
        kwargs = mock_boto.call_args.kwargs
        assert kwargs["aws_secret_access_key"] == "test-secret"


# ===========================================================================
# upload_file
# ===========================================================================

USER_ID = uuid.uuid4()
PDF_CT  = "application/pdf"
DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TestUploadFile:
    def _upload(self, content_type=PDF_CT, user_id=None):
        mock = _mock_client()
        file_obj = io.BytesIO(b"fake file content")
        with _patch_client(mock):
            key = upload_file(file_obj, content_type, user_id or USER_ID)
        return key, mock

    # ── Key format ────────────────────────────────────────────────────────────

    def test_returns_string_key(self):
        key, _ = self._upload()
        assert isinstance(key, str)

    def test_key_starts_with_uploads_prefix(self):
        key, _ = self._upload()
        assert key.startswith("uploads/")

    def test_key_contains_user_id(self):
        key, _ = self._upload(user_id=USER_ID)
        assert str(USER_ID) in key

    def test_key_ends_with_pdf_extension_for_pdf(self):
        key, _ = self._upload(content_type=PDF_CT)
        assert key.endswith(".pdf")

    def test_key_ends_with_docx_extension_for_docx(self):
        key, _ = self._upload(content_type=DOCX_CT)
        assert key.endswith(".docx")

    def test_key_format_is_uploads_userid_uuid_ext(self):
        key, _ = self._upload(user_id=USER_ID)
        # uploads/<user_id>/<uuid4>.pdf
        pattern = rf"^uploads/{USER_ID}/[0-9a-f\-]{{36}}\.pdf$"
        assert re.match(pattern, key), f"Key '{key}' did not match expected pattern"

    def test_each_upload_produces_unique_key(self):
        key1, _ = self._upload()
        key2, _ = self._upload()
        assert key1 != key2

    # ── S3 call arguments ─────────────────────────────────────────────────────

    def test_upload_uses_correct_bucket(self):
        _, mock = self._upload()
        call_kwargs = mock.upload_fileobj.call_args
        assert call_kwargs.args[1] == "test-bucket"

    def test_upload_sets_content_type_extra_arg(self):
        _, mock = self._upload(content_type=PDF_CT)
        extra = mock.upload_fileobj.call_args.kwargs["ExtraArgs"]
        assert extra["ContentType"] == PDF_CT

    def test_upload_sets_server_side_encryption(self):
        _, mock = self._upload()
        extra = mock.upload_fileobj.call_args.kwargs["ExtraArgs"]
        assert extra["ServerSideEncryption"] == "AES256"

    def test_upload_fileobj_called_once(self):
        _, mock = self._upload()
        mock.upload_fileobj.assert_called_once()

    # ── Error handling ────────────────────────────────────────────────────────

    def test_client_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_client_error("AccessDenied", "PutObject"))
        with _patch_client(mock):
            with pytest.raises(StorageError, match="Failed to upload"):
                upload_file(io.BytesIO(b"data"), PDF_CT, USER_ID)

    def test_botocore_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_FakeBotoCoreError())
        with _patch_client(mock):
            with pytest.raises(StorageError):
                upload_file(io.BytesIO(b"data"), PDF_CT, USER_ID)

    def test_storage_error_wraps_original_exception(self):
        original = _client_error("SlowDown", "PutObject")
        mock = _mock_client(side_effect=original)
        with _patch_client(mock):
            with pytest.raises(StorageError) as exc_info:
                upload_file(io.BytesIO(b"data"), PDF_CT, USER_ID)
        assert exc_info.value.__cause__ is original


# ===========================================================================
# delete_file
# ===========================================================================

class TestDeleteFile:
    def test_returns_none(self):
        mock = _mock_client()
        with _patch_client(mock):
            result = delete_file("uploads/some/key.pdf")
        assert result is None

    def test_calls_delete_object_once(self):
        mock = _mock_client()
        with _patch_client(mock):
            delete_file("uploads/some/key.pdf")
        mock.delete_object.assert_called_once()

    def test_uses_correct_bucket(self):
        mock = _mock_client()
        with _patch_client(mock):
            delete_file("uploads/some/key.pdf")
        call_kwargs = mock.delete_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"

    def test_passes_correct_key(self):
        mock = _mock_client()
        with _patch_client(mock):
            delete_file("uploads/user123/file.pdf")
        call_kwargs = mock.delete_object.call_args.kwargs
        assert call_kwargs["Key"] == "uploads/user123/file.pdf"

    def test_client_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_client_error("NoSuchBucket", "DeleteObject"))
        with _patch_client(mock):
            with pytest.raises(StorageError, match="Failed to delete"):
                delete_file("uploads/some/key.pdf")

    def test_botocore_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_FakeBotoCoreError())
        with _patch_client(mock):
            with pytest.raises(StorageError):
                delete_file("uploads/some/key.pdf")

    def test_storage_error_wraps_original_exception(self):
        original = _client_error("AccessDenied", "DeleteObject")
        mock = _mock_client(side_effect=original)
        with _patch_client(mock):
            with pytest.raises(StorageError) as exc_info:
                delete_file("uploads/some/key.pdf")
        assert exc_info.value.__cause__ is original


# ===========================================================================
# get_presigned_url
# ===========================================================================

FAKE_URL = "https://test-bucket.s3.amazonaws.com/uploads/user/file.pdf?X-Amz-Signature=abc"


class TestGetPresignedUrl:
    def test_returns_string(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            result = get_presigned_url("uploads/user/file.pdf")
        assert isinstance(result, str)

    def test_returns_url_from_boto(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            result = get_presigned_url("uploads/user/file.pdf")
        assert result == FAKE_URL

    def test_calls_generate_presigned_url_with_get_object(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            get_presigned_url("uploads/user/file.pdf")
        call_args = mock.generate_presigned_url.call_args
        assert call_args.args[0] == "get_object"

    def test_passes_correct_bucket_in_params(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            get_presigned_url("uploads/user/file.pdf")
        params = mock.generate_presigned_url.call_args.kwargs["Params"]
        assert params["Bucket"] == "test-bucket"

    def test_passes_correct_key_in_params(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            get_presigned_url("uploads/user/doc.docx")
        params = mock.generate_presigned_url.call_args.kwargs["Params"]
        assert params["Key"] == "uploads/user/doc.docx"

    def test_passes_expiry_from_settings(self):
        mock = _mock_client(generate_presigned_url=FAKE_URL)
        with _patch_client(mock):
            get_presigned_url("uploads/user/file.pdf")
        expires_in = mock.generate_presigned_url.call_args.kwargs["ExpiresIn"]
        assert expires_in == 3600  # matches FakeSettings.s3_presigned_url_expiry

    def test_client_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_client_error("AccessDenied", "GeneratePresignedUrl"))
        with _patch_client(mock):
            with pytest.raises(StorageError, match="Failed to generate presigned URL"):
                get_presigned_url("uploads/user/file.pdf")

    def test_botocore_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_FakeBotoCoreError())
        with _patch_client(mock):
            with pytest.raises(StorageError):
                get_presigned_url("uploads/user/file.pdf")

    def test_storage_error_wraps_original_exception(self):
        original = _client_error("SignatureDoesNotMatch", "GeneratePresignedUrl")
        mock = _mock_client(side_effect=original)
        with _patch_client(mock):
            with pytest.raises(StorageError) as exc_info:
                get_presigned_url("uploads/user/file.pdf")
        assert exc_info.value.__cause__ is original


# ===========================================================================
# download_file_bytes
# ===========================================================================

class TestDownloadFileBytes:
    def _make_get_object_response(self, body: bytes) -> dict:
        mock_body = MagicMock()
        mock_body.read.return_value = body
        return {"Body": mock_body}

    def test_returns_bytes(self):
        mock = _mock_client(get_object=self._make_get_object_response(b"file content"))
        with _patch_client(mock):
            result = download_file_bytes("uploads/user/file.pdf")
        assert isinstance(result, bytes)

    def test_returns_correct_content(self):
        content = b"PDF file bytes here"
        mock = _mock_client(get_object=self._make_get_object_response(content))
        with _patch_client(mock):
            result = download_file_bytes("uploads/user/file.pdf")
        assert result == content

    def test_calls_get_object_once(self):
        mock = _mock_client(get_object=self._make_get_object_response(b"data"))
        with _patch_client(mock):
            download_file_bytes("uploads/user/file.pdf")
        mock.get_object.assert_called_once()

    def test_passes_correct_bucket(self):
        mock = _mock_client(get_object=self._make_get_object_response(b"data"))
        with _patch_client(mock):
            download_file_bytes("uploads/user/file.pdf")
        call_kwargs = mock.get_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"

    def test_passes_correct_key(self):
        mock = _mock_client(get_object=self._make_get_object_response(b"data"))
        with _patch_client(mock):
            download_file_bytes("uploads/user/contract.pdf")
        call_kwargs = mock.get_object.call_args.kwargs
        assert call_kwargs["Key"] == "uploads/user/contract.pdf"

    def test_empty_file_returns_empty_bytes(self):
        mock = _mock_client(get_object=self._make_get_object_response(b""))
        with _patch_client(mock):
            result = download_file_bytes("uploads/user/empty.pdf")
        assert result == b""

    def test_client_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_client_error("NoSuchKey", "GetObject"))
        with _patch_client(mock):
            with pytest.raises(StorageError, match="Failed to download"):
                download_file_bytes("uploads/user/missing.pdf")

    def test_botocore_error_raises_storage_error(self):
        mock = _mock_client(side_effect=_FakeBotoCoreError())
        with _patch_client(mock):
            with pytest.raises(StorageError):
                download_file_bytes("uploads/user/file.pdf")

    def test_storage_error_wraps_original_exception(self):
        original = _client_error("NoSuchKey", "GetObject")
        mock = _mock_client(side_effect=original)
        with _patch_client(mock):
            with pytest.raises(StorageError) as exc_info:
                download_file_bytes("uploads/user/missing.pdf")
        assert exc_info.value.__cause__ is original