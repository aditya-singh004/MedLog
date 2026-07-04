from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import client_ip, current_receptionist
from app.core.enums import AppointmentStatus
from app.db.session import get_db
from app.models import Appointment, DoctorAvailability, DoctorProfile, Notification, ReceptionistProfile
from app.schemas.common import Message, NotificationOut
from app.schemas.patient import AppointmentOut
from app.schemas.receptionist import CancelRequest, ScheduleRequest
from app.services.appointment_service import ensure_doctor_slot_available, transition, validate_doctor_for_appointment
from app.services.audit_service import log_audit
from app.services.notification_service import create_notification, send_email


router = APIRouter(prefix="/api/receptionist", tags=["Receptionist"])


def hospital_appointment(db: Session, appointment_id: str, receptionist: ReceptionistProfile) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.hospital_id != receptionist.hospital_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


@router.get("/dashboard")
def dashboard(receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    appointments = db.scalars(select(Appointment).where(Appointment.hospital_id == receptionist.hospital_id)).all()
    return {
        "pending_requests": sum(a.status == AppointmentStatus.REQUESTED for a in appointments),
        "scheduled": sum(a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED) for a in appointments),
        "checked_in": sum(a.status == AppointmentStatus.CHECKED_IN for a in appointments),
        "cancelled": sum(a.status == AppointmentStatus.CANCELLED for a in appointments),
    }


@router.get("/appointment-requests", response_model=list[AppointmentOut])
def appointment_requests(receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    return db.scalars(select(Appointment).where(Appointment.hospital_id == receptionist.hospital_id, Appointment.status == AppointmentStatus.REQUESTED).order_by(Appointment.created_at)).all()


@router.get("/appointments", response_model=list[AppointmentOut])
def appointments(receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    return db.scalars(select(Appointment).where(Appointment.hospital_id == receptionist.hospital_id).order_by(Appointment.created_at.desc())).all()


def apply_schedule(db: Session, appointment: Appointment, receptionist: ReceptionistProfile, payload: ScheduleRequest, reschedule: bool, request: Request, background_tasks: BackgroundTasks):
    doctor = validate_doctor_for_appointment(db, appointment, payload.doctor_id)
    ensure_doctor_slot_available(db, doctor.id, payload.scheduled_start_time, payload.scheduled_end_time, appointment.id)
    transition(appointment, AppointmentStatus.RESCHEDULED if reschedule else AppointmentStatus.SCHEDULED)
    appointment.doctor_id = doctor.id
    appointment.receptionist_id = receptionist.id
    appointment.scheduled_start_time = payload.scheduled_start_time
    appointment.scheduled_end_time = payload.scheduled_end_time
    patient_user = appointment.patient.user
    title = "Appointment Rescheduled" if reschedule else "Appointment Scheduled"
    create_notification(db, patient_user.id, title, f"Your appointment with Dr. {doctor.user.full_name} at {appointment.hospital.name} has been scheduled for {payload.scheduled_start_time}.", resource_type="Appointment", resource_id=appointment.id)
    create_notification(db, doctor.user_id, "New Appointment Assigned", f"You have a new appointment with {patient_user.full_name} scheduled for {payload.scheduled_start_time}.", resource_type="Appointment", resource_id=appointment.id)
    background_tasks.add_task(send_email, patient_user.email, title, f"Your appointment with Dr. {doctor.user.full_name} is scheduled for {payload.scheduled_start_time}.")
    background_tasks.add_task(send_email, doctor.user.email, "New Appointment Assigned", f"You have an appointment with {patient_user.full_name} at {payload.scheduled_start_time}.")
    log_audit(db, actor_user_id=receptionist.user_id, action="APPOINTMENT_RESCHEDULED" if reschedule else "APPOINTMENT_SCHEDULED", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id, metadata={"doctor_id": doctor.id}, ip_address=client_ip(request))
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/schedule", response_model=AppointmentOut)
def schedule(appointment_id: str, payload: ScheduleRequest, request: Request, background_tasks: BackgroundTasks, receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    appointment = hospital_appointment(db, appointment_id, receptionist)
    return apply_schedule(db, appointment, receptionist, payload, False, request, background_tasks)


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule(appointment_id: str, payload: ScheduleRequest, request: Request, background_tasks: BackgroundTasks, receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    appointment = hospital_appointment(db, appointment_id, receptionist)
    return apply_schedule(db, appointment, receptionist, payload, True, request, background_tasks)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(appointment_id: str, payload: CancelRequest, request: Request, receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    appointment = hospital_appointment(db, appointment_id, receptionist)
    transition(appointment, AppointmentStatus.CANCELLED)
    appointment.cancellation_reason = payload.reason
    create_notification(db, appointment.patient.user_id, "Appointment Cancelled", f"Your appointment has been cancelled. Reason: {payload.reason}", resource_type="Appointment", resource_id=appointment.id)
    log_audit(db, actor_user_id=receptionist.user_id, action="APPOINTMENT_CANCELLED", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id, ip_address=client_ip(request))
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/appointments/{appointment_id}/check-in", response_model=AppointmentOut)
def check_in(appointment_id: str, request: Request, receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    appointment = hospital_appointment(db, appointment_id, receptionist)
    transition(appointment, AppointmentStatus.CHECKED_IN)
    log_audit(db, actor_user_id=receptionist.user_id, action="PATIENT_CHECKED_IN", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id, ip_address=client_ip(request))
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get("/doctors")
def doctors(receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    return db.scalars(select(DoctorProfile).where(DoctorProfile.hospital_id == receptionist.hospital_id, DoctorProfile.is_available.is_(True)).options(selectinload(DoctorProfile.user))).all()


@router.get("/doctors/{doctor_id}/availability")
def doctor_availability(doctor_id: str, receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    doctor = db.get(DoctorProfile, doctor_id)
    if not doctor or doctor.hospital_id != receptionist.hospital_id:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return db.scalars(select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor.id, DoctorAvailability.is_active.is_(True))).all()


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(receptionist: ReceptionistProfile = Depends(current_receptionist), db: Session = Depends(get_db)):
    return db.scalars(select(Notification).where(Notification.user_id == receptionist.user_id).order_by(Notification.created_at.desc())).all()
