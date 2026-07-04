from datetime import date, datetime, timezone
from pathlib import Path
from app.core.config import settings

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import AppointmentStatus, ConsentStatus, DocumentType, UserRole
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import (Appointment, AuditLog, ConsentRequest, Department, DoctorProfile, Hospital,
                        MedicalDocument, MedicalRecord, Notification, PatientProfile, ReceptionistProfile, User)
from app.schemas.doctor import MedicineCreate, PrescriptionCreate
from app.services.appointment_service import ensure_doctor_slot_available, transition, validate_doctor_for_appointment
from app.services.audit_service import log_audit
from app.services.consent_service import approve, require_active_consent
from app.services.file_service import save_medical_document
from app.services.notification_service import create_notification
from app.services.prescription_service import create_prescription


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def render(request: Request, name: str, **context):
    return templates.TemplateResponse(request=request, name=name, context=context)


def user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        user = db.get(User, decode_access_token(token).get("sub"))
        return user if user and user.is_active else None
    except ValueError:
        return None


def need_user(request: Request, db: Session, *roles: UserRole):
    user = user_from_request(request, db)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    if roles and user.role not in roles:
        return None, RedirectResponse(f"/{user.role.value.lower().replace('_admin', '/dashboard')}", status_code=303)
    return user, None


def flash_redirect(url: str, message: str, kind: str = "success"):
    from urllib.parse import quote
    return RedirectResponse(f"{url}?message={quote(message)}&kind={kind}", status_code=303)


@router.get("/")
def landing(request: Request, db: Session = Depends(get_db)):
    return render(request, "index.html", user=user_from_request(request, db))


@router.get("/login")
def login_page(request: Request):
    return render(request, "auth/login.html", user=None)


@router.post("/login")
async def web_login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    user = db.scalar(select(User).where(User.email == str(form.get("email", "")).lower()))
    if not user or not verify_password(str(form.get("password", "")), user.password_hash):
        return render(request, "auth/login.html", user=None, error="Invalid email or password")
    token = create_access_token(user.id, user.role.value)
    path = {UserRole.PATIENT: "/patient/dashboard", UserRole.RECEPTIONIST: "/receptionist/dashboard", UserRole.DOCTOR: "/doctor/dashboard"}.get(user.role, "/admin/dashboard")
    response = RedirectResponse(path, status_code=303)
    response.set_cookie(
    	"access_token",
    	token,
    	httponly=True,
    	secure=settings.cookie_secure,
    	samesite="lax",
    	max_age=28800,
    )
    log_audit(db, actor_user_id=user.id, action="LOGIN", resource_type="User", resource_id=user.id, ip_address=request.client.host if request.client else None)
    db.commit()
    return response


@router.get("/register")
def register_page(request: Request):
    return render(request, "auth/register.html", user=None)


@router.post("/register")
async def web_register(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    email, password = str(form.get("email", "")).lower(), str(form.get("password", ""))
    if len(password) < 8:
        return render(request, "auth/register.html", user=None, error="Password must be at least 8 characters")
    if db.scalar(select(User).where(User.email == email)):
        return render(request, "auth/register.html", user=None, error="Email is already registered")
    dob = date.fromisoformat(str(form["date_of_birth"])) if form.get("date_of_birth") else None
    user = User(email=email, password_hash=hash_password(password), full_name=str(form.get("full_name", "")), phone=str(form.get("phone", "")) or None, role=UserRole.PATIENT)
    user.patient_profile = PatientProfile(date_of_birth=dob, gender=str(form.get("gender", "")) or None)
    db.add(user); db.commit()
    return flash_redirect("/login", "Registration complete. Please sign in.")


@router.get("/logout")
def web_logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/patient/dashboard")
def patient_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    p = user.patient_profile
    appointments = db.scalars(select(Appointment).where(Appointment.patient_id == p.id)).all()
    consents = db.scalars(select(ConsentRequest).where(ConsentRequest.patient_id == p.id)).all()
    records = db.scalars(select(MedicalRecord).where(MedicalRecord.patient_id == p.id)).all()
    notifications = db.scalars(select(Notification).where(Notification.user_id == user.id)).all()
    cards = [("Upcoming appointments", sum(a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED) for a in appointments)), ("Pending consent requests", sum(c.status == ConsentStatus.PENDING for c in consents)), ("Medical records", len(records)), ("Notifications", len(notifications))]
    return render(request, "patient/dashboard.html", user=user, cards=cards, appointments=appointments[-5:])


@router.get("/patient/hospitals")
def patient_hospitals(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    hospitals = db.scalars(select(Hospital).where(Hospital.is_active.is_(True)).options(selectinload(Hospital.departments))).all()
    return render(request, "patient/hospitals.html", user=user, hospitals=hospitals)


@router.get("/patient/appointments/request")
def request_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    hospitals = db.scalars(select(Hospital).where(Hospital.is_active.is_(True)).options(selectinload(Hospital.departments))).all()
    return render(request, "patient/request.html", user=user, hospitals=hospitals)


@router.post("/patient/appointments/request")
async def web_request_appointment(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    form = await request.form(); hospital = db.get(Hospital, str(form["hospital_id"])); department = db.get(Department, str(form["department_id"]))
    if not hospital or not department or department.hospital_id != hospital.id:
        return flash_redirect("/patient/appointments/request", "Invalid hospital or department", "danger")
    appointment = Appointment(patient_id=user.patient_profile.id, hospital_id=hospital.id, department_id=department.id, preferred_date=date.fromisoformat(str(form["preferred_date"])), preferred_time_window=str(form["preferred_time_window"]), reason_for_visit=str(form["reason_for_visit"]), symptoms=str(form["symptoms"]), notes=str(form.get("notes", "")) or None)
    db.add(appointment); db.flush()
    for receptionist in db.scalars(select(ReceptionistProfile).where(ReceptionistProfile.hospital_id == hospital.id)).all():
        create_notification(db, receptionist.user_id, "New Appointment Request", f"A patient has requested an appointment for {department.name} on {appointment.preferred_date}.", resource_type="Appointment", resource_id=appointment.id)
    log_audit(db, actor_user_id=user.id, action="APPOINTMENT_REQUESTED", resource_type="Appointment", resource_id=appointment.id, patient_id=user.patient_profile.id)
    db.commit()
    return flash_redirect("/patient/appointments", "Appointment request submitted")


@router.get("/patient/appointments")
def patient_appointments(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    items = db.scalars(select(Appointment).where(Appointment.patient_id == user.patient_profile.id).options(selectinload(Appointment.hospital), selectinload(Appointment.doctor).selectinload(DoctorProfile.user)).order_by(Appointment.created_at.desc())).all()
    return render(request, "patient/appointments.html", user=user, appointments=items)


@router.get("/patient/medical-history")
def patient_history(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    records = db.scalars(select(MedicalRecord).where(MedicalRecord.patient_id == user.patient_profile.id).options(selectinload(MedicalRecord.doctor).selectinload(DoctorProfile.user), selectinload(MedicalRecord.hospital), selectinload(MedicalRecord.prescription)).order_by(MedicalRecord.created_at.desc())).all()
    return render(request, "patient/history.html", user=user, records=records)


@router.get("/patient/documents")
def patient_documents(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    docs = db.scalars(select(MedicalDocument).where(MedicalDocument.patient_id == user.patient_profile.id).order_by(MedicalDocument.created_at.desc())).all()
    return render(request, "patient/documents.html", user=user, documents=docs, document_types=list(DocumentType))


@router.post("/patient/documents")
async def web_upload_document(request: Request, document_type: DocumentType = Form(...), description: str | None = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    try: path, size = await save_medical_document(file)
    except HTTPException as exc: return flash_redirect("/patient/documents", exc.detail, "danger")
    doc = MedicalDocument(patient_id=user.patient_profile.id, uploaded_by_user_id=user.id, document_type=document_type, file_name=file.filename or "document", file_path=path, file_size=size, content_type=file.content_type or "", description=description)
    try:
        db.add(doc); db.flush(); log_audit(db, actor_user_id=user.id, action="REPORT_UPLOADED", resource_type="MedicalDocument", resource_id=doc.id, patient_id=user.patient_profile.id); db.commit()
    except Exception:
        db.rollback()
        delete_file(path)
        raise
    return flash_redirect("/patient/documents", "Document uploaded")


@router.get("/patient/consents")
def patient_consents(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    items = db.scalars(select(ConsentRequest).where(ConsentRequest.patient_id == user.patient_profile.id).options(selectinload(ConsentRequest.doctor).selectinload(DoctorProfile.user), selectinload(ConsentRequest.hospital)).order_by(ConsentRequest.created_at.desc())).all()
    return render(request, "patient/consents.html", user=user, consents=items)


@router.post("/patient/consents/{consent_id}/{action}")
def web_consent_action(consent_id: str, action: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    consent = db.get(ConsentRequest, consent_id)
    if not consent or consent.patient_id != user.patient_profile.id: return flash_redirect("/patient/consents", "Consent not found", "danger")
    now = datetime.now(timezone.utc)
    try:
        if action == "approve": approve(consent, 24)
        elif action == "reject" and consent.status == ConsentStatus.PENDING: consent.status, consent.rejected_at = ConsentStatus.REJECTED, now
        elif action == "revoke" and consent.status == ConsentStatus.APPROVED: consent.status, consent.revoked_at = ConsentStatus.REVOKED, now
        else: raise ValueError("Invalid consent action")
    except (HTTPException, ValueError) as exc: return flash_redirect("/patient/consents", getattr(exc, "detail", str(exc)), "danger")
    log_audit(db, actor_user_id=user.id, action=f"CONSENT_{action.upper()}D" if action != "approve" else "CONSENT_APPROVED", resource_type="ConsentRequest", resource_id=consent.id, patient_id=consent.patient_id); db.commit()
    return flash_redirect("/patient/consents", f"Consent {action}d")


@router.get("/patient/notifications")
def patient_notifications(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.PATIENT)
    if redirect: return redirect
    items = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())).all()
    return render(request, "notifications.html", user=user, notifications=items)


@router.get("/receptionist/dashboard")
def receptionist_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    r = user.receptionist_profile
    items = db.scalars(select(Appointment).where(Appointment.hospital_id == r.hospital_id)).all()
    cards = [("Pending requests", sum(a.status == AppointmentStatus.REQUESTED for a in items)), ("Scheduled", sum(a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED) for a in items)), ("Checked in", sum(a.status == AppointmentStatus.CHECKED_IN for a in items)), ("Cancelled", sum(a.status == AppointmentStatus.CANCELLED for a in items))]
    return render(request, "receptionist/dashboard.html", user=user, cards=cards, appointments=items[-8:])


@router.get("/receptionist/appointments/requests")
def receptionist_requests(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    items = db.scalars(select(Appointment).where(Appointment.hospital_id == user.receptionist_profile.hospital_id, Appointment.status == AppointmentStatus.REQUESTED).options(selectinload(Appointment.patient).selectinload(PatientProfile.user), selectinload(Appointment.department))).all()
    return render(request, "receptionist/requests.html", user=user, appointments=items)


@router.get("/receptionist/appointments/schedule/{appointment_id}")
def schedule_page(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    r = user.receptionist_profile; appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.hospital_id != r.hospital_id: return flash_redirect("/receptionist/appointments/requests", "Appointment not found", "danger")
    doctors = db.scalars(select(DoctorProfile).where(DoctorProfile.hospital_id == r.hospital_id, DoctorProfile.department_id == appointment.department_id, DoctorProfile.is_available.is_(True)).options(selectinload(DoctorProfile.user))).all()
    return render(request, "receptionist/schedule.html", user=user, appointment=appointment, doctors=doctors)


@router.post("/receptionist/appointments/schedule/{appointment_id}")
async def web_schedule(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    r = user.receptionist_profile; appointment = db.get(Appointment, appointment_id); form = await request.form()
    if not appointment or appointment.hospital_id != r.hospital_id: return flash_redirect("/receptionist/appointments/requests", "Appointment not found", "danger")
    try:
        start, end = datetime.fromisoformat(str(form["scheduled_start_time"])), datetime.fromisoformat(str(form["scheduled_end_time"]))
        doctor = validate_doctor_for_appointment(db, appointment, str(form["doctor_id"])); ensure_doctor_slot_available(db, doctor.id, start, end, appointment.id)
        transition(appointment, AppointmentStatus.SCHEDULED if appointment.status == AppointmentStatus.REQUESTED else AppointmentStatus.RESCHEDULED)
    except (HTTPException, ValueError) as exc: return flash_redirect(f"/receptionist/appointments/schedule/{appointment_id}", getattr(exc, "detail", str(exc)), "danger")
    appointment.doctor_id, appointment.receptionist_id, appointment.scheduled_start_time, appointment.scheduled_end_time = doctor.id, r.id, start, end
    create_notification(db, appointment.patient.user_id, "Appointment Scheduled", f"Your appointment with Dr. {doctor.user.full_name} at {appointment.hospital.name} is scheduled for {start}.", resource_type="Appointment", resource_id=appointment.id)
    create_notification(db, doctor.user_id, "New Appointment Assigned", f"You have an appointment with {appointment.patient.user.full_name} at {start}.", resource_type="Appointment", resource_id=appointment.id)
    log_audit(db, actor_user_id=user.id, action="APPOINTMENT_SCHEDULED", resource_type="Appointment", resource_id=appointment.id, patient_id=appointment.patient_id); db.commit()
    return flash_redirect("/receptionist/queue", "Appointment scheduled")


@router.get("/receptionist/queue")
def receptionist_queue(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    items = db.scalars(select(Appointment).where(Appointment.hospital_id == user.receptionist_profile.hospital_id).options(selectinload(Appointment.patient).selectinload(PatientProfile.user), selectinload(Appointment.doctor).selectinload(DoctorProfile.user)).order_by(Appointment.scheduled_start_time)).all()
    return render(request, "receptionist/queue.html", user=user, appointments=items)


@router.post("/receptionist/appointments/{appointment_id}/check-in")
def web_check_in(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    appointment = db.get(Appointment, appointment_id)
    if not appointment or appointment.hospital_id != user.receptionist_profile.hospital_id: return flash_redirect("/receptionist/queue", "Appointment not found", "danger")
    try: transition(appointment, AppointmentStatus.CHECKED_IN)
    except HTTPException as exc: return flash_redirect("/receptionist/queue", exc.detail, "danger")
    db.commit(); return flash_redirect("/receptionist/queue", "Patient checked in")


@router.get("/receptionist/notifications")
def receptionist_notifications(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.RECEPTIONIST)
    if redirect: return redirect
    items = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())).all()
    return render(request, "notifications.html", user=user, notifications=items)


@router.get("/doctor/dashboard")
def doctor_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    d = user.doctor_profile; items = db.scalars(select(Appointment).where(Appointment.doctor_id == d.id)).all()
    cards = [("Scheduled", sum(a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.RESCHEDULED) for a in items)), ("Checked in", sum(a.status == AppointmentStatus.CHECKED_IN for a in items)), ("In consultation", sum(a.status == AppointmentStatus.IN_CONSULTATION for a in items)), ("Completed", sum(a.status == AppointmentStatus.COMPLETED for a in items))]
    return render(request, "doctor/dashboard.html", user=user, cards=cards, appointments=items[-8:])


@router.get("/doctor/appointments")
def doctor_appointments(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    items = db.scalars(select(Appointment).where(Appointment.doctor_id == user.doctor_profile.id).options(selectinload(Appointment.patient).selectinload(PatientProfile.user)).order_by(Appointment.scheduled_start_time.desc())).all()
    return render(request, "doctor/appointments.html", user=user, appointments=items)


@router.get("/doctor/appointments/{appointment_id}")
def doctor_appointment(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    item = db.get(Appointment, appointment_id)
    if not item or item.doctor_id != user.doctor_profile.id: return flash_redirect("/doctor/appointments", "Appointment not found", "danger")
    consents = db.scalars(select(ConsentRequest).where(ConsentRequest.patient_id == item.patient_id, ConsentRequest.doctor_id == user.doctor_profile.id).order_by(ConsentRequest.created_at.desc())).all()
    return render(request, "doctor/detail.html", user=user, appointment=item, consents=consents)


@router.post("/doctor/appointments/{appointment_id}/start")
def web_start_consultation(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    item = db.get(Appointment, appointment_id)
    if not item or item.doctor_id != user.doctor_profile.id: return flash_redirect("/doctor/appointments", "Appointment not found", "danger")
    try: transition(item, AppointmentStatus.IN_CONSULTATION)
    except HTTPException as exc: return flash_redirect(f"/doctor/appointments/{item.id}", exc.detail, "danger")
    db.commit(); return flash_redirect(f"/doctor/appointments/{item.id}", "Consultation started")


@router.post("/doctor/appointments/{appointment_id}/request-consent")
async def web_request_consent(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    item = db.get(Appointment, appointment_id); form = await request.form()
    if not item or item.doctor_id != user.doctor_profile.id: return flash_redirect("/doctor/appointments", "Appointment not found", "danger")
    pending = db.scalar(select(ConsentRequest).where(ConsentRequest.patient_id == item.patient_id, ConsentRequest.doctor_id == user.doctor_profile.id, ConsentRequest.status == ConsentStatus.PENDING))
    if pending: return flash_redirect(f"/doctor/appointments/{item.id}", "A request is already pending", "danger")
    consent = ConsentRequest(patient_id=item.patient_id, doctor_id=user.doctor_profile.id, hospital_id=item.hospital_id, appointment_id=item.id, requested_reason=str(form.get("requested_reason", "Continuity of care")))
    db.add(consent); db.flush(); create_notification(db, item.patient.user_id, "Medical History Access Request", f"Dr. {user.full_name} has requested access to your medical history.", resource_type="ConsentRequest", resource_id=consent.id); db.commit()
    return flash_redirect(f"/doctor/appointments/{item.id}", "Consent requested")


@router.get("/doctor/patients/{patient_id}/history")
def doctor_history(patient_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    linked = db.scalar(select(Appointment.id).where(Appointment.patient_id == patient_id, Appointment.doctor_id == user.doctor_profile.id))
    if not linked: return flash_redirect("/doctor/appointments", "Patient not found", "danger")
    try: require_active_consent(db, patient_id, user.doctor_profile.id)
    except HTTPException as exc: return flash_redirect("/doctor/appointments", exc.detail, "danger")
    records = db.scalars(select(MedicalRecord).where(MedicalRecord.patient_id == patient_id).options(selectinload(MedicalRecord.doctor).selectinload(DoctorProfile.user), selectinload(MedicalRecord.hospital)).order_by(MedicalRecord.created_at.desc())).all()
    patient = db.get(PatientProfile, patient_id); log_audit(db, actor_user_id=user.id, action="PATIENT_HISTORY_VIEWED", resource_type="PatientProfile", resource_id=patient_id, patient_id=patient_id); db.commit()
    return render(request, "doctor/history.html", user=user, patient=patient, records=records)


@router.get("/doctor/appointments/{appointment_id}/prescription")
def prescription_page(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    item = db.get(Appointment, appointment_id)
    if not item or item.doctor_id != user.doctor_profile.id: return flash_redirect("/doctor/appointments", "Appointment not found", "danger")
    return render(request, "doctor/prescription.html", user=user, appointment=item)


@router.post("/doctor/appointments/{appointment_id}/prescription")
async def web_prescription(appointment_id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    item = db.get(Appointment, appointment_id); form = await request.form()
    if not item or item.doctor_id != user.doctor_profile.id: return flash_redirect("/doctor/appointments", "Appointment not found", "danger")
    medicine = MedicineCreate(medicine_name=str(form["medicine_name"]), dosage=str(form["dosage"]), frequency=str(form["frequency"]), duration=str(form["duration"]), timing=str(form.get("timing", "")) or None, special_instructions=str(form.get("special_instructions", "")) or None)
    payload = PrescriptionCreate(chief_complaint=str(form.get("chief_complaint", "")) or None, diagnosis=str(form["diagnosis"]), clinical_notes=str(form.get("clinical_notes", "")) or None, recommended_tests=str(form.get("recommended_tests", "")) or None, general_instructions=str(form.get("general_instructions", "")) or None, follow_up_date=date.fromisoformat(str(form["follow_up_date"])) if form.get("follow_up_date") else None, medicines=[medicine])
    try: prescription = create_prescription(db, item, user.doctor_profile.id, payload)
    except HTTPException as exc: return flash_redirect(f"/doctor/appointments/{item.id}/prescription", exc.detail, "danger")
    db.flush(); create_notification(db, item.patient.user_id, "Prescription Added", f"Dr. {user.full_name} added a prescription to your medical record.", resource_type="Prescription", resource_id=prescription.id); log_audit(db, actor_user_id=user.id, action="PRESCRIPTION_CREATED", resource_type="Prescription", resource_id=prescription.id, patient_id=item.patient_id); db.commit()
    return flash_redirect("/doctor/appointments", "Prescription saved and consultation completed")


@router.get("/doctor/notifications")
def doctor_notifications(request: Request, db: Session = Depends(get_db)):
    user, redirect = need_user(request, db, UserRole.DOCTOR)
    if redirect: return redirect
    items = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())).all()
    return render(request, "notifications.html", user=user, notifications=items)


def admin_guard(request, db): return need_user(request, db, UserRole.SUPER_ADMIN, UserRole.HOSPITAL_ADMIN)


def web_admin_hospitals(db: Session, user: User):
    query = select(Hospital)
    if user.role == UserRole.HOSPITAL_ADMIN:
        query = query.where(Hospital.id == user.hospital_id)
    return db.scalars(query.order_by(Hospital.name)).all()


def web_admin_can_manage(user: User, hospital_id: str) -> bool:
    return user.role == UserRole.SUPER_ADMIN or user.hospital_id == hospital_id


@router.get("/admin/dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    hospitals = web_admin_hospitals(db, user); hospital_ids = [h.id for h in hospitals]
    doctors = db.scalars(select(DoctorProfile).where(DoctorProfile.hospital_id.in_(hospital_ids))).all() if hospital_ids else []
    receptionists = db.scalars(select(ReceptionistProfile).where(ReceptionistProfile.hospital_id.in_(hospital_ids))).all() if hospital_ids else []
    cards = [("Hospitals", len(hospitals)), ("Doctors", len(doctors)), ("Receptionists", len(receptionists)), ("Staff", len(doctors) + len(receptionists))]
    return render(request, "admin/dashboard.html", user=user, cards=cards)


@router.get("/admin/hospitals")
def admin_hospitals(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    return render(request, "admin/hospitals.html", user=user, hospitals=web_admin_hospitals(db, user))


@router.post("/admin/hospitals")
async def web_create_hospital(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    if user.role != UserRole.SUPER_ADMIN: return flash_redirect("/admin/hospitals", "Only super admins can create hospitals", "danger")
    form = await request.form(); hospital = Hospital(name=str(form["name"]), city=str(form["city"]), address=str(form["address"]), phone=str(form.get("phone", "")) or None, email=str(form.get("email", "")) or None, registration_number=str(form["registration_number"])); db.add(hospital)
    try: db.commit()
    except Exception: db.rollback(); return flash_redirect("/admin/hospitals", "Registration number already exists", "danger")
    return flash_redirect("/admin/hospitals", "Hospital created")


@router.get("/admin/departments")
def admin_departments(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    hospital_ids = [h.id for h in web_admin_hospitals(db, user)]
    hospitals = db.scalars(select(Hospital).where(Hospital.id.in_(hospital_ids)).options(selectinload(Hospital.departments))).all()
    return render(request, "admin/departments.html", user=user, hospitals=hospitals)


@router.post("/admin/departments")
async def web_create_department(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    form = await request.form(); hospital_id = str(form["hospital_id"])
    if not web_admin_can_manage(user, hospital_id): return flash_redirect("/admin/departments", "Cannot manage another hospital", "danger")
    db.add(Department(hospital_id=hospital_id, name=str(form["name"]), description=str(form.get("description", "")) or None))
    try: db.commit()
    except Exception: db.rollback(); return flash_redirect("/admin/departments", "Department already exists", "danger")
    return flash_redirect("/admin/departments", "Department created")


@router.get("/admin/doctors")
def admin_doctors(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    hospital_ids = [h.id for h in web_admin_hospitals(db, user)]
    doctors = db.scalars(select(DoctorProfile).where(DoctorProfile.hospital_id.in_(hospital_ids)).options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.hospital), selectinload(DoctorProfile.department))).all(); hospitals = db.scalars(select(Hospital).where(Hospital.id.in_(hospital_ids)).options(selectinload(Hospital.departments))).all()
    return render(request, "admin/doctors.html", user=user, doctors=doctors, hospitals=hospitals)


@router.post("/admin/doctors")
async def web_create_doctor(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    f = await request.form(); hospital_id = str(f["hospital_id"])
    if not web_admin_can_manage(user, hospital_id): return flash_redirect("/admin/doctors", "Cannot manage another hospital", "danger")
    department = db.get(Department, str(f["department_id"]))
    if not department or department.hospital_id != hospital_id: return flash_redirect("/admin/doctors", "Invalid department", "danger")
    account = User(email=str(f["email"]).lower(), password_hash=hash_password(str(f["password"])), full_name=str(f["full_name"]), role=UserRole.DOCTOR); account.doctor_profile = DoctorProfile(hospital_id=hospital_id, department_id=department.id, specialization=str(f["specialization"]), medical_license_number=str(f["medical_license_number"]), experience_years=int(f.get("experience_years", 0)), consultation_fee=float(f.get("consultation_fee", 0))); db.add(account)
    try: db.commit()
    except Exception: db.rollback(); return flash_redirect("/admin/doctors", "Email or license already exists", "danger")
    return flash_redirect("/admin/doctors", "Doctor created")


@router.get("/admin/receptionists")
def admin_receptionists(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    hospitals = web_admin_hospitals(db, user); hospital_ids = [h.id for h in hospitals]
    staff = db.scalars(select(ReceptionistProfile).where(ReceptionistProfile.hospital_id.in_(hospital_ids)).options(selectinload(ReceptionistProfile.user), selectinload(ReceptionistProfile.hospital))).all()
    return render(request, "admin/receptionists.html", user=user, receptionists=staff, hospitals=hospitals)


@router.post("/admin/receptionists")
async def web_create_receptionist(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    f = await request.form(); hospital_id = str(f["hospital_id"])
    if not web_admin_can_manage(user, hospital_id): return flash_redirect("/admin/receptionists", "Cannot manage another hospital", "danger")
    account = User(email=str(f["email"]).lower(), password_hash=hash_password(str(f["password"])), full_name=str(f["full_name"]), role=UserRole.RECEPTIONIST); account.receptionist_profile = ReceptionistProfile(hospital_id=hospital_id, employee_code=str(f["employee_code"])); db.add(account)
    try: db.commit()
    except Exception: db.rollback(); return flash_redirect("/admin/receptionists", "Email or employee code already exists", "danger")
    return flash_redirect("/admin/receptionists", "Receptionist created")


@router.get("/admin/audit-logs")
def admin_audit_logs(request: Request, db: Session = Depends(get_db)):
    user, redirect = admin_guard(request, db)
    if redirect: return redirect
    if user.role != UserRole.SUPER_ADMIN: return flash_redirect("/admin/dashboard", "System-wide audit logs require super-admin access", "danger")
    logs = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()
    return render(request, "admin/audit.html", user=user, logs=logs)
