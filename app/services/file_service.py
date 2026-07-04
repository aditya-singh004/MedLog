import logging
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import boto3
from fastapi import HTTPException, UploadFile

from app.core.config import settings


ALLOWED_CONTENT_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
logger = logging.getLogger("medivault.storage")


def _s3_client():
    return boto3.client("s3", region_name=settings.aws_region)


async def save_medical_document(file: UploadFile) -> tuple[str, int]:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF, PNG, JPG, and JPEG files are allowed")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="File exceeds the 10MB limit")
    extension = ALLOWED_CONTENT_TYPES[file.content_type]
    object_name = f"{uuid4()}{extension}"

    if settings.storage_backend == "s3":
        if not settings.s3_documents_bucket:
            raise RuntimeError("S3_DOCUMENTS_BUCKET is required when STORAGE_BACKEND=s3")
        prefix = settings.s3_documents_prefix.strip("/")
        key = f"{prefix}/{object_name}" if prefix else object_name
        try:
            _s3_client().put_object(
                Bucket=settings.s3_documents_bucket,
                Key=key,
                Body=content,
                ContentType=file.content_type,
                ServerSideEncryption="AES256",
            )
        except Exception:
            logger.exception("Medical document upload to object storage failed")
            raise HTTPException(status_code=503, detail="Document storage is temporarily unavailable")
        return f"s3://{settings.s3_documents_bucket}/{key}", len(content)

    path = settings.upload_dir / object_name
    path.write_bytes(content)
    return str(path), len(content)


def delete_file(path: str) -> None:
    if path.startswith("s3://"):
        parsed = urlparse(path)
        if not settings.s3_documents_bucket or parsed.netloc != settings.s3_documents_bucket:
            logger.error("Refusing to delete an object outside the configured document bucket")
            return
        try:
            _s3_client().delete_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        except Exception:
            logger.exception("Failed to clean up an uncommitted document object")
        return
    Path(path).unlink(missing_ok=True)
