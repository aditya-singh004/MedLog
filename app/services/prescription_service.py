from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus, RecordType
from app.models import Appointment, MedicalRecord, Prescription, PrescriptionMedicine
from app.schemas.doctor import PrescriptionCreate
from app.services.appointment_service import transition


def create_prescription(db: Session, appointment: Appointment, doctor_id: str, payload: PrescriptionCreate) -> Prescription:
    if appointment.doctor_id != doctor_id:
        raise HTTPException(status_code=403, detail="Only the assigned doctor can prescribe")
    if appointment.status != AppointmentStatus.IN_CONSULTATION:
        raise HTTPException(status_code=400, detail="Appointment must be in consultation before prescribing")
    if appointment.medical_record:
        raise HTTPException(status_code=409, detail="A medical record already exists for this appointment")
    record = MedicalRecord(
        patient_id=appointment.patient_id,
        appointment_id=appointment.id,
        hospital_id=appointment.hospital_id,
        doctor_id=doctor_id,
        record_type=RecordType.CONSULTATION,
        chief_complaint=payload.chief_complaint,
        diagnosis=payload.diagnosis,
        clinical_notes=payload.clinical_notes,
        recommended_tests=payload.recommended_tests,
        follow_up_date=payload.follow_up_date,
    )
    db.add(record)
    db.flush()
    prescription = Prescription(
        medical_record_id=record.id,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        doctor_id=doctor_id,
        general_instructions=payload.general_instructions,
        follow_up_date=payload.follow_up_date,
    )
    prescription.medicines = [PrescriptionMedicine(**medicine.model_dump()) for medicine in payload.medicines]
    db.add(prescription)
    transition(appointment, AppointmentStatus.COMPLETED)
    return prescription
