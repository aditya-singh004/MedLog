from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AppointmentStatus, ConsentStatus, DocumentType


class AppointmentRequest(BaseModel):
    hospital_id: str
    department_id: str
    preferred_date: date
    preferred_time_window: str = Field(min_length=2, max_length=80)
    reason_for_visit: str = Field(min_length=2)
    symptoms: str = Field(min_length=2)
    notes: str | None = None


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    hospital_id: str
    department_id: str
    doctor_id: str | None
    preferred_date: date
    preferred_time_window: str
    scheduled_start_time: datetime | None
    scheduled_end_time: datetime | None
    reason_for_visit: str
    symptoms: str
    notes: str | None
    status: AppointmentStatus
    created_at: datetime


class ConsentDecision(BaseModel):
    duration_hours: int | None = Field(default=24, ge=1, le=24 * 365)
    custom_expires_at: datetime | None = None


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    doctor_id: str
    hospital_id: str
    appointment_id: str | None
    status: ConsentStatus
    requested_reason: str
    requested_at: datetime
    expires_at: datetime | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_type: DocumentType
    file_name: str
    file_size: int
    content_type: str
    description: str | None
    created_at: datetime
