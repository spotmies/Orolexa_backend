# app/services/storage/object_store.py
"""
S3-compatible object storage (Railway Bucket) helpers.

Images keep their existing "/uploads/<key>" URLs; when a bucket is configured the
bytes live in the bucket under <key> instead of on local disk, and the
/api/auth/images endpoints proxy them (Railway buckets are private).
"""
import logging
import mimetypes
from functools import lru_cache
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """True when all bucket settings are present."""
    return bool(
        settings.S3_BUCKET_NAME
        and settings.S3_ENDPOINT_URL
        and settings.AWS_ACCESS_KEY_ID
        and settings.AWS_SECRET_ACCESS_KEY
    )


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        region_name=settings.S3_REGION or "auto",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": settings.S3_ADDRESSING_STYLE},
        ),
    )


def key_from_url(url_or_key: str) -> str:
    """Convert '/uploads/profiles/x.jpg' (or 'profiles/x.jpg') to 'profiles/x.jpg'."""
    key = url_or_key
    if key.startswith("/uploads/"):
        key = key[len("/uploads/"):]
    return key.lstrip("/")


def put(key: str, data: bytes, content_type: Optional[str] = None) -> bool:
    try:
        _client().put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=data,
            ContentType=content_type or mimetypes.guess_type(key)[0] or "application/octet-stream",
        )
        return True
    except Exception as e:
        logger.error(f"Error uploading {key} to bucket: {e}")
        return False


def get(key: str) -> Optional[bytes]:
    """Return object bytes, or None if missing/unavailable."""
    try:
        obj = _client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return obj["Body"].read()
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404"):
            logger.error(f"Error reading {key} from bucket: {e}")
        return None


def delete(key: str) -> bool:
    try:
        _client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return True
    except Exception as e:
        logger.error(f"Error deleting {key} from bucket: {e}")
        return False


def delete_prefix(prefix: str, keep: Optional[str] = None) -> None:
    """Delete every object under prefix except `keep`."""
    try:
        paginator = _client().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.S3_BUCKET_NAME, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"] != keep:
                    delete(obj["Key"])
    except Exception as e:
        logger.error(f"Error cleaning bucket prefix {prefix}: {e}")
