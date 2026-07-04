from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConsentStatus
from app.db.database import Base, TimestampMixin, UUIDMixin, utcnow


class ConsentRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "consent_requests"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patient_profiles.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctor_profiles.id"), index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"))
    status: Mapped[ConsentStatus] = mapped_column(Enum(ConsentStatus), default=ConsentStatus.PENDING, index=True)
    requested_reason: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    patient = relationship("PatientProfile")
    doctor = relationship("DoctorProfile")
    hospital = relationship("Hospital")
    appointment = relationship("Appointment")
