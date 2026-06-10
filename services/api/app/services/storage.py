"""Media storage service.

Uploads to Cloudflare R2 when R2_BUCKET_NAME is configured, otherwise
falls back to local disk (for development with docker-compose).
"""

from __future__ import annotations

from pathlib import Path


def upload_media(file_bytes: bytes, key: str, content_type: str) -> str:
    """Store *file_bytes* at *key* and return its public URL.

    key should be a relative path like ``cherokee-choice/1/scene_1.png``.
    """
    from app.core.config import settings

    if settings.R2_BUCKET_NAME:
        return _upload_r2(file_bytes, key, content_type, settings)
    return _save_local(file_bytes, key, settings)


def _upload_r2(file_bytes: bytes, key: str, content_type: str, settings: object) -> str:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def _save_local(file_bytes: bytes, key: str, settings: object) -> str:
    dest = Path("media") / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)
    return f"{settings.MEDIA_BASE_URL.rstrip('/')}/{key}"
