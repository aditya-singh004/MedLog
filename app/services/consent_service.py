from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ConsentStatus
from app.models import ConsentRequest


def aware_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def approve(consent: ConsentRequest, duration_hours: int = 24, custom_expires_at: datetime | None = None) -> None:
    if consent.status != ConsentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending consent can be approved")
    now = aware_utcnow()
    expiry = custom_expires_at or now + timedelta(hours=duration_hours)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now:
        raise HTTPException(status_code=400, detail="Consent expiry must be in the future")
    consent.status = ConsentStatus.APPROVED
    consent.approved_at = now
    consent.expires_at = expiry


def has_active_consent(db: Session, patient_id: str, doctor_id: str) -> bool:
    now = aware_utcnow()
    consents = db.scalars(select(ConsentRequest).where(
        ConsentRequest.patient_id == patient_id,
        ConsentRequest.doctor_id == doctor_id,
        ConsentRequest.status == ConsentStatus.APPROVED,
    )).all()
    active = False
    for consent in consents:
        expiry = consent.expires_at
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry and expiry > now:
            active = True
        else:
            consent.status = ConsentStatus.EXPIRED
    return active


def require_active_consent(db: Session, patient_id: str, doctor_id: str) -> None:
    if not has_active_consent(db, patient_id, doctor_id):
        raise HTTPException(status_code=403, detail="Active patient consent is required")
