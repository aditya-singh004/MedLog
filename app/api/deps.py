from collections.abc import Callable

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import DoctorProfile, PatientProfile, ReceptionistProfile, User


bearer = HTTPBearer(auto_error=False)


def get_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    access_token: str | None = Cookie(default=None),
) -> str:
    token = credentials.credentials if credentials else access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return token


def get_current_user(token: str = Depends(get_token), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
        user = db.get(User, payload.get("sub"))
    except ValueError:
        user = None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive account")
    return user


def require_roles(*roles: UserRole) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency


def current_patient(user: User = Depends(require_roles(UserRole.PATIENT))) -> PatientProfile:
    if not user.patient_profile:
        raise HTTPException(status_code=403, detail="Patient profile missing")
    return user.patient_profile


def current_doctor(user: User = Depends(require_roles(UserRole.DOCTOR))) -> DoctorProfile:
    if not user.doctor_profile:
        raise HTTPException(status_code=403, detail="Doctor profile missing")
    return user.doctor_profile


def current_receptionist(user: User = Depends(require_roles(UserRole.RECEPTIONIST))) -> ReceptionistProfile:
    if not user.receptionist_profile:
        raise HTTPException(status_code=403, detail="Receptionist profile missing")
    return user.receptionist_profile


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
