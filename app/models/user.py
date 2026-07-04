from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.db.database import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True, nullable=False)
    hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    patient_profile: Mapped["PatientProfile | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    doctor_profile: Mapped["DoctorProfile | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    receptionist_profile: Mapped["ReceptionistProfile | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    managed_hospital = relationship("Hospital", foreign_keys=[hospital_id])


class PatientProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(30))
    blood_group: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))
    known_allergies: Mapped[str | None] = mapped_column(Text)
    chronic_conditions: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="patient_profile")
    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    medical_records = relationship("MedicalRecord", back_populates="patient", cascade="all, delete-orphan")


class DoctorProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), index=True)
    specialization: Mapped[str] = mapped_column(String(120))
    medical_license_number: Mapped[str] = mapped_column(String(80), unique=True)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="doctor_profile")
    hospital = relationship("Hospital", back_populates="doctors")
    department = relationship("Department", back_populates="doctors")
    appointments = relationship("Appointment", back_populates="doctor")
    availability = relationship("DoctorAvailability", back_populates="doctor", cascade="all, delete-orphan")


class ReceptionistProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "receptionist_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), index=True)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True)

    user: Mapped[User] = relationship(back_populates="receptionist_profile")
    hospital = relationship("Hospital", back_populates="receptionists")
    appointments = relationship("Appointment", back_populates="receptionist")
