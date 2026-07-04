from datetime import date, datetime

from pydantic import BaseModel, Field


class ConsentRequestCreate(BaseModel):
    requested_reason: str = Field(min_length=3)
    appointment_id: str | None = None


class MedicineCreate(BaseModel):
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    timing: str | None = None
    special_instructions: str | None = None


class PrescriptionCreate(BaseModel):
    chief_complaint: str | None = None
    diagnosis: str = Field(min_length=2)
    clinical_notes: str | None = None
    recommended_tests: str | None = None
    general_instructions: str | None = None
    follow_up_date: date | None = None
    medicines: list[MedicineCreate] = Field(default_factory=list)


class MedicineOut(MedicineCreate):
    id: str


class MedicalRecordOut(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    patient_id: str
    appointment_id: str | None
    hospital_id: str
    doctor_id: str
    diagnosis: str
    clinical_notes: str | None
    recommended_tests: str | None
    follow_up_date: date | None
    created_at: datetime
