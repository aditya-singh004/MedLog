from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import client_ip, current_doctor
from app.core.enums import AppointmentStatus, ConsentStatus
from app.db.session import get_db
from app.models import Appointment, ConsentRequest, DoctorProfile, MedicalRecord, Notification, PatientProfile, Prescription
from app.schemas.common import Message, NotificationOut
from app.schemas.doctor import ConsentRequestCreate, MedicalRecordOut, PrescriptionCreate
from app.schemas.patient import AppointmentOut, ConsentOut
from app.services.appointment_service import transition
from app.services.audit_service import log_audit
from app.services.consent_service import require_active_consent
from app.services.notification_service import create_notification, send_email
from app.services.prescription_service import create_prescription


router = APIRouter(prefix="/api/doctor", tags=["Doctor"])


def assigned_appointment(db: Session, appointment_id: str, doctor: DoctorProfile) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.doctor_id != doctor.id:
        raise HTTPException(status_code=404, detail="Assigned appointment not found")
    return appointment


def ensure_patient_relationship(db: Session, patient_id: str, doctor: DoctorProfile) -> PatientProfile:
    patient = db.get(PatientProfile, patient_id)
    linked = db.scalar(select(Appointment.id).where(Appointment.patient_id == patient_id, Appointment.doctor_id == doctor.id).limit(1))
    if not patient or not linked:
        raise HTTPException(status_code=404, detail="Patient not found in your assigned appointments")
    return patient


@router.get("/dashboard")
def dashboard(doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    items = db.scalars(select(Appointment).where(Appointment.doctor_id == doctor.id)).all()
    return {
        "scheduled": sum(a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED) for a in items),
        "checked_in": sum(a.status == AppointmentStatus.CHECKED_IN for a in items),
        "in_consultation": sum(a.status == AppointmentStatus.IN_CONSULTATION for a in items),
        "completed": sum(a.status == AppointmentStatus.COMPLETED for a in items),
    }


@router.get("/appointments", response_model=list[AppointmentOut])
def appointments(doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    return db.scalars(select(Appointment).where(Appointment.doctor_id == doctor.id).order_by(Appointment.scheduled_start_time.desc())).all()


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def appointment_detail(appointment_id: str, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    return assigned_appointment(db, appointment_id, doctor)


@router.post("/appointments/{appointment_id}/start", response_model=AppointmentOut)
def start_consultation(appointment_id: str, request: Request, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    appointment = assigned_appointment(db, appointment_id, doctor)
    transition(appointment, AppointmentStatus.IN_CONSULTATION)
    log_audit(db, actor_user_id=doctor.user_id, action="CONSULTATION_STARTED", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id, ip_address=client_ip(request))
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/complete", response_model=Message)
def complete_consultation(appointment_id: str, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    appointment = assigned_appointment(db, appointment_id, doctor)
    if appointment.status == AppointmentStatus.COMPLETED:
        return Message(message="Consultation completed")
    raise HTTPException(status_code=400, detail="Save consultation notes and prescription to complete the appointment")


@router.post("/patients/{patient_id}/consent-request", response_model=ConsentOut, status_code=201)
def request_consent(patient_id: str, payload: ConsentRequestCreate, request: Request, background_tasks: BackgroundTasks, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    patient = ensure_patient_relationship(db, patient_id, doctor)
    if payload.appointment_id:
        appointment = assigned_appointment(db, payload.appointment_id, doctor)
        if appointment.patient_id != patient.id:
            raise HTTPException(status_code=400, detail="Appointment does not belong to this patient")
    pending = db.scalar(select(ConsentRequest).where(ConsentRequest.patient_id == patient.id, ConsentRequest.doctor_id == doctor.id, ConsentRequest.status == ConsentStatus.PENDING))
    if pending:
        raise HTTPException(status_code=409, detail="A consent request is already pending")
    consent = ConsentRequest(patient_id=patient.id, doctor_id=doctor.id, hospital_id=doctor.hospital_id, appointment_id=payload.appointment_id, requested_reason=payload.requested_reason)
    db.add(consent)
    db.flush()
    create_notification(db, patient.user_id, "Medical History Access Request", f"Dr. {doctor.user.full_name} from {doctor.hospital.name} has requested access to your medical history.", resource_type="ConsentRequest", resource_id=consent.id)
    background_tasks.add_task(send_email, patient.user.email, "Medical History Access Request", f"Dr. {doctor.user.full_name} from {doctor.hospital.name} requested access to your medical history.")
    log_audit(db, actor_user_id=doctor.user_id, action="CONSENT_REQUESTED", resource_type="ConsentRequest", resource_id=consent.id, patient_id=patient.id, ip_address=client_ip(request))
    db.commit()
    db.refresh(consent)
    return consent


@router.get("/patients/{patient_id}/medical-history", response_model=list[MedicalRecordOut])
def medical_history(patient_id: str, request: Request, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    patient = ensure_patient_relationship(db, patient_id, doctor)
    require_active_consent(db, patient.id, doctor.id)
    log_audit(db, actor_user_id=doctor.user_id, action="PATIENT_HISTORY_VIEWED", resource_type="PatientProfile", resource_id=patient.id, patient_id=patient.id, metadata={"doctor_id": doctor.id, "hospital_id": doctor.hospital_id}, ip_address=client_ip(request))
    records = db.scalars(select(MedicalRecord).where(MedicalRecord.patient_id == patient.id).order_by(MedicalRecord.created_at.desc())).all()
    db.commit()
    return records


@router.post("/appointments/{appointment_id}/prescription", status_code=201)
def prescribe(appointment_id: str, payload: PrescriptionCreate, request: Request, background_tasks: BackgroundTasks, doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    appointment = assigned_appointment(db, appointment_id, doctor)
    prescription = create_prescription(db, appointment, doctor.id, payload)
    db.flush()
    create_notification(db, appointment.patient.user_id, "Prescription Added", f"Dr. {doctor.user.full_name} has added a prescription to your medical record.", resource_type="Prescription", resource_id=prescription.id)
    background_tasks.add_task(send_email, appointment.patient.user.email, "Prescription Added", f"Dr. {doctor.user.full_name} has added a prescription to your medical record.")
    log_audit(db, actor_user_id=doctor.user_id, action="PRESCRIPTION_CREATED", resource_type="Prescription", resource_id=prescription.id, patient_id=appointment.patient_id, ip_address=client_ip(request))
    log_audit(db, actor_user_id=doctor.user_id, action="APPOINTMENT_COMPLETED", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id, ip_address=client_ip(request))
    db.commit()
    return {"id": prescription.id, "appointment_id": appointment.id, "status": appointment.status, "message": "Prescription saved and consultation completed"}


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(doctor: DoctorProfile = Depends(current_doctor), db: Session = Depends(get_db)):
    return db.scalars(select(Notification).where(Notification.user_id == doctor.user_id).order_by(Notification.created_at.desc())).all()
