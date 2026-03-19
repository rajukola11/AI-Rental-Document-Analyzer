import uuid
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging import get_logger

logger = get_logger(__name__)

def _client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def upload_file(file_obj: BinaryIO, content_type: str, user_id: uuid.UUID) -> str:
    """
    Upload file to S3. Returns the S3 key (not the full URL).
    Key format: uploads/{user_id}/{uuid}.{ext}
    """
    ext = content_type.split("/")[-1].replace("vnd.openxmlformats-officedocument.wordprocessingml.document", "docx")
    key = f"uploads/{user_id}/{uuid.uuid4()}.{ext}"

    try:
        _client().upload_fileobj(
            file_obj,
            settings.s3_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
        logger.info("Uploaded to S3", extra={"key": key, "user_id": str(user_id)})
        return key
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed: %s", exc)
        raise StorageError(f"Failed to upload file: {exc}") from exc


def delete_file(key: str) -> None:
    """Delete a file from S3 by key."""
    try:
        _client().delete_object(Bucket=settings.s3_bucket_name, Key=key)
        logger.info("Deleted from S3", extra={"key": key})
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 delete failed: %s", exc)
        raise StorageError(f"Failed to delete file: {exc}") from exc


def get_presigned_url(key: str) -> str:
    """Generate a short-lived presigned URL for secure file access."""
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": key},
            ExpiresIn=settings.s3_presigned_url_expiry,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Presigned URL failed: %s", exc)
        raise StorageError(f"Failed to generate presigned URL: {exc}") from exc


def download_file_bytes(key: str) -> bytes:
    """Download a file from S3 and return its raw bytes (used by Celery worker)."""
    try:
        response = _client().get_object(Bucket=settings.s3_bucket_name, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 download failed: %s", exc)
        raise StorageError(f"Failed to download file: {exc}") from exc