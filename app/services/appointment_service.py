from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus
from app.models import Appointment, DoctorProfile


ALLOWED_TRANSITIONS = {
    AppointmentStatus.REQUESTED: {AppointmentStatus.SCHEDULED, AppointmentStatus.CANCELLED},
    AppointmentStatus.SCHEDULED: {AppointmentStatus.CHECKED_IN, AppointmentStatus.RESCHEDULED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW},
    AppointmentStatus.RESCHEDULED: {AppointmentStatus.SCHEDULED, AppointmentStatus.CHECKED_IN, AppointmentStatus.CANCELLED},
    AppointmentStatus.CHECKED_IN: {AppointmentStatus.IN_CONSULTATION},
    AppointmentStatus.IN_CONSULTATION: {AppointmentStatus.COMPLETED},
}


def transition(appointment: Appointment, new_status: AppointmentStatus) -> None:
    if new_status not in ALLOWED_TRANSITIONS.get(appointment.status, set()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid transition: {appointment.status.value} -> {new_status.value}")
    appointment.status = new_status


def ensure_doctor_slot_available(db: Session, doctor_id: str, start, end, exclude_id: str | None = None) -> None:
    query = select(Appointment).where(
        Appointment.doctor_id == doctor_id,
        Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED, AppointmentStatus.CHECKED_IN, AppointmentStatus.IN_CONSULTATION]),
        Appointment.scheduled_start_time < end,
        Appointment.scheduled_end_time > start,
    )
    if exclude_id:
        query = query.where(Appointment.id != exclude_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="Doctor already has an overlapping appointment")


def validate_doctor_for_appointment(db: Session, appointment: Appointment, doctor_id: str) -> DoctorProfile:
    doctor = db.get(DoctorProfile, doctor_id)
    if not doctor or doctor.hospital_id != appointment.hospital_id or doctor.department_id != appointment.department_id or not doctor.is_available:
        raise HTTPException(status_code=400, detail="Doctor is unavailable or not assigned to this hospital and department")
    return doctor
