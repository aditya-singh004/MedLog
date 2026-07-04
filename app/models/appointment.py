from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AppointmentStatus
from app.db.database import Base, TimestampMixin, UUIDMixin


class DoctorAvailability(UUIDMixin, Base):
    __tablename__ = "doctor_availability"

    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctor_profiles.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    doctor = relationship("DoctorProfile", back_populates="availability")


class Appointment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointment_patient_status", "patient_id", "status"),
        Index("ix_appointment_hospital_status", "hospital_id", "status"),
    )

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), index=True)
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctor_profiles.id"), index=True)
    receptionist_id: Mapped[str | None] = mapped_column(ForeignKey("receptionist_profiles.id"))
    preferred_date: Mapped[date] = mapped_column(Date)
    preferred_time_window: Mapped[str] = mapped_column(String(80))
    scheduled_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    scheduled_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason_for_visit: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AppointmentStatus] = mapped_column(Enum(AppointmentStatus), default=AppointmentStatus.REQUESTED, index=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    patient = relationship("PatientProfile", back_populates="appointments")
    hospital = relationship("Hospital")
    department = relationship("Department")
    doctor = relationship("DoctorProfile", back_populates="appointments")
    receptionist = relationship("ReceptionistProfile", back_populates="appointments")
    medical_record = relationship("MedicalRecord", back_populates="appointment", uselist=False)
