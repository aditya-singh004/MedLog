from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class HospitalCreate(BaseModel):
    name: str
    city: str
    address: str
    phone: str | None = None
    email: EmailStr | None = None
    registration_number: str


class HospitalUpdate(BaseModel):
    name: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class DepartmentCreate(BaseModel):
    name: str
    description: str | None = None


class DoctorCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    phone: str | None = None
    hospital_id: str
    department_id: str
    specialization: str
    medical_license_number: str
    experience_years: int = Field(default=0, ge=0)
    consultation_fee: Decimal = Field(default=0, ge=0)


class ReceptionistCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    phone: str | None = None
    hospital_id: str
    employee_code: str


class HospitalAdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    phone: str | None = None
    hospital_id: str
