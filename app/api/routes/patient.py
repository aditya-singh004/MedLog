from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import client_ip, current_patient, get_current_user
from app.core.enums import AppointmentStatus, ConsentStatus, DocumentType, NotificationStatus, UserRole
from app.db.session import get_db
from app.models import (Appointment, ConsentRequest, Department, Hospital, MedicalDocument,
                        MedicalRecord, Notification, PatientProfile, ReceptionistProfile, User)
from app.schemas.common import Message, NotificationOut
from app.schemas.doctor import MedicalRecordOut
from app.schemas.patient import AppointmentOut, AppointmentRequest, ConsentDecision, ConsentOut, DocumentOut
from app.services.audit_service import log_audit
from app.services.consent_service import approve
from app.services.file_service import delete_file, save_medical_document
from app.services.notification_service import create_notification, send_email


router = APIRouter(prefix="/api/patient", tags=["Patient"])


@router.get("/dashboard")
def dashboard(patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return {
        "upcoming_appointments": db.scalar(select(func.count()).select_from(Appointment).where(Appointment.patient_id == patient.id, Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED]))),
        "pending_consents": db.scalar(select(func.count()).select_from(ConsentRequest).where(ConsentRequest.patient_id == patient.id, ConsentRequest.status == ConsentStatus.PENDING)),
        "medical_records": db.scalar(select(func.count()).select_from(MedicalRecord).where(MedicalRecord.patient_id == patient.id)),
        "unread_notifications": db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == patient.user_id, Notification.status != NotificationStatus.READ)),
    }


@router.get("/hospitals")
def hospitals(_: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Hospital).where(Hospital.is_active.is_(True)).order_by(Hospital.name)).all()


@router.get("/hospitals/{hospital_id}/departments")
def departments(hospital_id: str, _: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Department).where(Department.hospital_id == hospital_id, Department.is_active.is_(True)).order_by(Department.name)).all()


@router.post("/appointments/request", response_model=AppointmentOut, status_code=201)
def request_appointment(payload: AppointmentRequest, request: Request, background_tasks: BackgroundTasks, patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    hospital = db.get(Hospital, payload.hospital_id)
    department = db.get(Department, payload.department_id)
    if not hospital or not hospital.is_active or not department or department.hospital_id != hospital.id or not department.is_active:
        raise HTTPException(status_code=400, detail="Invalid hospital or department")
    appointment = Appointment(patient_id=patient.id, **payload.model_dump())
    db.add(appointment)
    db.flush()
    receptionists = db.scalars(select(ReceptionistProfile).where(ReceptionistProfile.hospital_id == hospital.id).options(selectinload(ReceptionistProfile.user))).all()
    for receptionist in receptionists:
        create_notification(db, receptionist.user_id, "New Appointment Request", f"A patient has requested an appointment for {department.name} on {payload.preferred_date}.", resource_type="Appointment", resource_id=appointment.id)
        background_tasks.add_task(send_email, receptionist.user.email, "New Appointment Request", f"A patient has requested an appointment for {department.name} on {payload.preferred_date}.")
    log_audit(db, actor_user_id=patient.user_id, action="APPOINTMENT_REQUESTED", resource_type="Appointment", resource_id=appointment.id, patient_id=patient.id, metadata={"hospital_id": hospital.id}, ip_address=client_ip(request))
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get("/appointments", response_model=list[AppointmentOut])
def appointments(patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Appointment).where(Appointment.patient_id == patient.id).order_by(Appointment.created_at.desc())).all()


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def appointment_detail(appointment_id: str, patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    item = db.get(Appointment, appointment_id)
    if not item or item.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return item


@router.get("/medical-history", response_model=list[MedicalRecordOut])
def medical_history(patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(MedicalRecord).where(MedicalRecord.patient_id == patient.id).order_by(MedicalRecord.created_at.desc())).all()


@router.post("/documents/upload", response_model=DocumentOut, status_code=201)
async def upload_document(request: Request, document_type: DocumentType = Form(...), description: str | None = Form(None), appointment_id: str | None = Form(None), file: UploadFile = File(...), patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    if appointment_id:
        appointment = db.get(Appointment, appointment_id)
        if not appointment or appointment.patient_id != patient.id:
            raise HTTPException(status_code=404, detail="Appointment not found")
    path, size = await save_medical_document(file)
    document = MedicalDocument(patient_id=patient.id, uploaded_by_user_id=patient.user_id, appointment_id=appointment_id, document_type=document_type, file_name=file.filename or "document", file_path=path, file_size=size, content_type=file.content_type or "application/octet-stream", description=description)
    try:
        db.add(document)
        db.flush()
        log_audit(db, actor_user_id=patient.user_id, action="REPORT_UPLOADED", resource_type="MedicalDocument", resource_id=document.id, patient_id=patient.id, ip_address=client_ip(request))
        db.commit()
    except Exception:
        db.rollback()
        delete_file(path)
        raise
    db.refresh(document)
    return document


@router.get("/documents", response_model=list[DocumentOut])
def documents(patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(MedicalDocument).where(MedicalDocument.patient_id == patient.id).order_by(MedicalDocument.created_at.desc())).all()


@router.get("/consent-requests", response_model=list[ConsentOut])
def consents(patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    return db.scalars(select(ConsentRequest).where(ConsentRequest.patient_id == patient.id).order_by(ConsentRequest.requested_at.desc())).all()


def owned_consent(db: Session, request_id: str, patient_id: str) -> ConsentRequest:
    consent = db.get(ConsentRequest, request_id)
    if not consent or consent.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Consent request not found")
    return consent


@router.post("/consent-requests/{request_id}/approve", response_model=ConsentOut)
def approve_consent(request_id: str, payload: ConsentDecision, request: Request, background_tasks: BackgroundTasks, patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    consent = owned_consent(db, request_id, patient.id)
    approve(consent, payload.duration_hours or 24, payload.custom_expires_at)
    create_notification(db, consent.doctor.user_id, "Consent Approved", f"{patient.user.full_name} has approved access to their medical history until {consent.expires_at}.", resource_type="ConsentRequest", resource_id=consent.id)
    background_tasks.add_task(send_email, consent.doctor.user.email, "Consent Approved", f"{patient.user.full_name} has approved access until {consent.expires_at}.")
    log_audit(db, actor_user_id=patient.user_id, action="CONSENT_APPROVED", resource_type="ConsentRequest", resource_id=consent.id, patient_id=patient.id, ip_address=client_ip(request))
    db.commit()
    db.refresh(consent)
    return consent


@router.post("/consent-requests/{request_id}/reject", response_model=ConsentOut)
def reject_consent(request_id: str, request: Request, patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    consent = owned_consent(db, request_id, patient.id)
    if consent.status != ConsentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only pending consent can be rejected")
    consent.status, consent.rejected_at = ConsentStatus.REJECTED, datetime.now(timezone.utc)
    log_audit(db, actor_user_id=patient.user_id, action="CONSENT_REJECTED", resource_type="ConsentRequest", resource_id=consent.id, patient_id=patient.id, ip_address=client_ip(request))
    db.commit()
    db.refresh(consent)
    return consent


@router.post("/consent-requests/{request_id}/revoke", response_model=ConsentOut)
def revoke_consent(request_id: str, request: Request, patient: PatientProfile = Depends(current_patient), db: Session = Depends(get_db)):
    consent = owned_consent(db, request_id, patient.id)
    if consent.status != ConsentStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved consent can be revoked")
    consent.status, consent.revoked_at = ConsentStatus.REVOKED, datetime.now(timezone.utc)
    log_audit(db, actor_user_id=patient.user_id, action="CONSENT_REVOKED", resource_type="ConsentRequest", resource_id=consent.id, patient_id=patient.id, ip_address=client_ip(request))
    db.commit()
    db.refresh(consent)
    return consent


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Patient access required")
    return db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())).all()


@router.post("/notifications/{notification_id}/read", response_model=Message)
def mark_read(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notification = db.get(Notification, notification_id)
    if not notification or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.status, notification.read_at = NotificationStatus.READ, datetime.now(timezone.utc)
    db.commit()
    return Message(message="Notification marked as read")
