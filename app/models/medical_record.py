from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DocumentType, RecordType
from app.db.database import Base, TimestampMixin, UUIDMixin, utcnow


class MedicalRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "medical_records"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"), unique=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctor_profiles.id"), index=True)
    record_type: Mapped[RecordType] = mapped_column(Enum(RecordType), default=RecordType.CONSULTATION)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    clinical_notes: Mapped[str | None] = mapped_column(Text)
    recommended_tests: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date)

    patient = relationship("PatientProfile", back_populates="medical_records")
    appointment = relationship("Appointment", back_populates="medical_record")
    hospital = relationship("Hospital")
    doctor = relationship("DoctorProfile")
    prescription = relationship("Prescription", back_populates="medical_record", uselist=False, cascade="all, delete-orphan")


class Prescription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prescriptions"

    medical_record_id: Mapped[str] = mapped_column(ForeignKey("medical_records.id"), unique=True)
    appointment_id: Mapped[str] = mapped_column(ForeignKey("appointments.id"), unique=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctor_profiles.id"), index=True)
    general_instructions: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date)

    medical_record = relationship("MedicalRecord", back_populates="prescription")
    medicines = relationship("PrescriptionMedicine", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionMedicine(UUIDMixin, Base):
    __tablename__ = "prescription_medicines"

    prescription_id: Mapped[str] = mapped_column(ForeignKey("prescriptions.id", ondelete="CASCADE"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(150))
    dosage: Mapped[str] = mapped_column(String(80))
    frequency: Mapped[str] = mapped_column(String(100))
    duration: Mapped[str] = mapped_column(String(100))
    timing: Mapped[str | None] = mapped_column(String(100))
    special_instructions: Mapped[str | None] = mapped_column(Text)
    prescription = relationship("Prescription", back_populates="medicines")


class MedicalDocument(UUIDMixin, Base):
    __tablename__ = "medical_documents"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"))
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"))
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patient = relationship("PatientProfile")
