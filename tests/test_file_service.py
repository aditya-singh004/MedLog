from io import BytesIO

import pytest
from fastapi import UploadFile

from app.core.config import settings
from app.services import file_service


@pytest.mark.asyncio
async def test_local_document_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    upload = UploadFile(filename="report.pdf", file=BytesIO(b"safe test document"), headers={"content-type": "application/pdf"})

    stored_path, size = await file_service.save_medical_document(upload)

    assert size == 18
    assert BytesIO(open(stored_path, "rb").read()).getvalue() == b"safe test document"


@pytest.mark.asyncio
async def test_s3_document_storage_is_encrypted(monkeypatch):
    calls = []

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_documents_bucket", "private-test-bucket")
    monkeypatch.setattr(settings, "s3_documents_prefix", "medical-documents")
    monkeypatch.setattr(file_service, "_s3_client", lambda: FakeS3())
    upload = UploadFile(filename="scan.png", file=BytesIO(b"image bytes"), headers={"content-type": "image/png"})

    stored_path, size = await file_service.save_medical_document(upload)

    assert stored_path.startswith("s3://private-test-bucket/medical-documents/")
    assert size == 11
    assert calls[0]["ServerSideEncryption"] == "AES256"
    assert calls[0]["ContentType"] == "image/png"


@pytest.mark.asyncio
async def test_rejects_unsupported_document_type():
    upload = UploadFile(filename="malware.exe", file=BytesIO(b"nope"), headers={"content-type": "application/octet-stream"})

    with pytest.raises(Exception) as exc:
        await file_service.save_medical_document(upload)

    assert exc.value.status_code == 400
