from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AuditLog, Department, DoctorProfile, Hospital, ReceptionistProfile, User
from app.schemas.admin import DepartmentCreate, DoctorCreate, HospitalAdminCreate, HospitalCreate, HospitalUpdate, ReceptionistCreate
from app.schemas.auth import UserOut


router = APIRouter(prefix="/api/admin", tags=["Administration"])
admin_user = require_roles(UserRole.SUPER_ADMIN, UserRole.HOSPITAL_ADMIN)
super_admin = require_roles(UserRole.SUPER_ADMIN)


def ensure_hospital_access(user: User, hospital_id: str) -> None:
    if user.role != UserRole.SUPER_ADMIN and user.hospital_id != hospital_id:
        raise HTTPException(status_code=403, detail="Hospital admins can only manage their assigned hospital")


@router.get("/dashboard")
def dashboard(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    hospital_filter = None if user.role == UserRole.SUPER_ADMIN else user.hospital_id
    return {
        "hospitals": len(db.scalars(select(Hospital) if not hospital_filter else select(Hospital).where(Hospital.id == hospital_filter)).all()),
        "doctors": len(db.scalars(select(DoctorProfile) if not hospital_filter else select(DoctorProfile).where(DoctorProfile.hospital_id == hospital_filter)).all()),
        "receptionists": len(db.scalars(select(ReceptionistProfile) if not hospital_filter else select(ReceptionistProfile).where(ReceptionistProfile.hospital_id == hospital_filter)).all()),
        "users": len(db.scalars(select(User)).all()),
    }


@router.post("/hospitals", status_code=201)
def create_hospital(payload: HospitalCreate, _: User = Depends(super_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Hospital).where(Hospital.registration_number == payload.registration_number)):
        raise HTTPException(status_code=409, detail="Registration number already exists")
    hospital = Hospital(**payload.model_dump())
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    return hospital


@router.get("/hospitals")
def list_hospitals(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    query = select(Hospital).order_by(Hospital.name)
    if user.role == UserRole.HOSPITAL_ADMIN:
        query = query.where(Hospital.id == user.hospital_id)
    return db.scalars(query).all()


@router.put("/hospitals/{hospital_id}")
def update_hospital(hospital_id: str, payload: HospitalUpdate, _: User = Depends(super_admin), db: Session = Depends(get_db)):
    hospital = db.get(Hospital, hospital_id)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(hospital, key, value)
    db.commit()
    db.refresh(hospital)
    return hospital


@router.post("/hospitals/{hospital_id}/departments", status_code=201)
def create_department(hospital_id: str, payload: DepartmentCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    ensure_hospital_access(user, hospital_id)
    if not db.get(Hospital, hospital_id):
        raise HTTPException(status_code=404, detail="Hospital not found")
    department = Department(hospital_id=hospital_id, **payload.model_dump())
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


@router.post("/doctors", response_model=UserOut, status_code=201)
def create_doctor(payload: DoctorCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    ensure_hospital_access(user, payload.hospital_id)
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email already exists")
    department = db.get(Department, payload.department_id)
    if not department or department.hospital_id != payload.hospital_id:
        raise HTTPException(status_code=400, detail="Department does not belong to hospital")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name, phone=payload.phone, role=UserRole.DOCTOR)
    user.doctor_profile = DoctorProfile(hospital_id=payload.hospital_id, department_id=payload.department_id, specialization=payload.specialization, medical_license_number=payload.medical_license_number, experience_years=payload.experience_years, consultation_fee=payload.consultation_fee)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/receptionists", response_model=UserOut, status_code=201)
def create_receptionist(payload: ReceptionistCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    ensure_hospital_access(user, payload.hospital_id)
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email already exists")
    if not db.get(Hospital, payload.hospital_id):
        raise HTTPException(status_code=404, detail="Hospital not found")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name, phone=payload.phone, role=UserRole.RECEPTIONIST)
    user.receptionist_profile = ReceptionistProfile(hospital_id=payload.hospital_id, employee_code=payload.employee_code)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def users(user: User = Depends(admin_user), db: Session = Depends(get_db)):
    if user.role == UserRole.SUPER_ADMIN:
        return db.scalars(select(User).order_by(User.created_at.desc())).all()
    return db.scalars(select(User).outerjoin(DoctorProfile, DoctorProfile.user_id == User.id).outerjoin(ReceptionistProfile, ReceptionistProfile.user_id == User.id).where((DoctorProfile.hospital_id == user.hospital_id) | (ReceptionistProfile.hospital_id == user.hospital_id) | (User.id == user.id)).order_by(User.created_at.desc())).unique().all()


@router.get("/audit-logs")
def audit_logs(_: User = Depends(super_admin), db: Session = Depends(get_db)):
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()


@router.post("/hospital-admins", response_model=UserOut, status_code=201)
def create_hospital_admin(payload: HospitalAdminCreate, _: User = Depends(super_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email already exists")
    if not db.get(Hospital, payload.hospital_id):
        raise HTTPException(status_code=404, detail="Hospital not found")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name, phone=payload.phone, role=UserRole.HOSPITAL_ADMIN, hospital_id=payload.hospital_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
