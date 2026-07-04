from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings

from app.api.deps import client_ip, get_current_user
from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import PatientProfile, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.schemas.common import Message
from app.services.audit_service import log_audit


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), full_name=payload.full_name, phone=payload.phone, role=UserRole.PATIENT)
    user.patient_profile = PatientProfile(date_of_birth=payload.date_of_birth, gender=payload.gender)
    db.add(user)
    db.flush()
    log_audit(db, actor_user_id=user.id, action="PATIENT_REGISTERED", resource_type="User", resource_id=user.id, patient_id=user.patient_profile.id, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.role.value)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=8 * 60 * 60)
    log_audit(db, actor_user_id=user.id, action="LOGIN", resource_type="User", resource_id=user.id, ip_address=client_ip(request))
    db.commit()
    return TokenResponse(access_token=token)


@router.post("/logout", response_model=Message)
def logout(response: Response):
    response.delete_cookie("access_token")
    return Message(message="Logged out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
