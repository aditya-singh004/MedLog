from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.core.enums import AppointmentStatus, RecordType, UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (Appointment, Department, DoctorAvailability, DoctorProfile, Hospital,
                        MedicalRecord, PatientProfile, Prescription, PrescriptionMedicine,
                        ReceptionistProfile, User)


HOSPITALS = [
    ("CityCare Hospital", "Jaipur", "MV-JAI-001"),
    ("Metro Health Clinic", "Delhi", "MV-DEL-001"),
    ("Sunrise Multispeciality Hospital", "Mumbai", "MV-MUM-001"),
]
DEPARTMENTS = ["General Medicine", "Cardiology", "Dermatology", "Orthopedics"]


def seed():
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == "admin@medivault.com")):
            print("Seed data already exists; nothing changed.")
            return
        admin = User(email="admin@medivault.com", password_hash=hash_password("Admin@123"), full_name="MedLog Super Admin", role=UserRole.SUPER_ADMIN)
        db.add(admin)
        hospitals = []
        for name, city, registration in HOSPITALS:
            hospital = Hospital(name=name, city=city, address=f"Central district, {city}", phone="+91 98765 43210", email=f"contact@{name.lower().replace(' ', '')}.example", registration_number=registration)
            hospital.departments = [Department(name=name, description=f"{name} services") for name in DEPARTMENTS]
            db.add(hospital); hospitals.append(hospital)
        db.flush()
        doctors = []
        for index in range(2):
            user = User(email=f"doctor{index + 1}@medivault.com", password_hash=hash_password("Doctor@123"), full_name=["Aarav Sharma", "Meera Kapoor"][index], phone=f"+91 90000000{index + 1}", role=UserRole.DOCTOR)
            user.doctor_profile = DoctorProfile(hospital_id=hospitals[index].id, department_id=hospitals[index].departments[index].id, specialization=DEPARTMENTS[index], medical_license_number=f"MCI-MV-{1001 + index}", experience_years=8 + index, consultation_fee=800 + index * 200)
            db.add(user); db.flush(); doctors.append(user.doctor_profile)
            for day in range(0, 6): db.add(DoctorAvailability(doctor_id=user.doctor_profile.id, day_of_week=day, start_time=time(9), end_time=time(17), slot_duration_minutes=30))
        receptionists = []
        for index in range(2):
            user = User(email=f"reception{index + 1}@medivault.com", password_hash=hash_password("Reception@123"), full_name=["Riya Singh", "Kabir Verma"][index], role=UserRole.RECEPTIONIST)
            user.receptionist_profile = ReceptionistProfile(hospital_id=hospitals[index].id, employee_code=f"REC-{index + 1:03d}")
            db.add(user); db.flush(); receptionists.append(user.receptionist_profile)
        patient_user = User(email="patient@medivault.com", password_hash=hash_password("Patient@123"), full_name="Ananya Gupta", phone="+91 99999 00000", role=UserRole.PATIENT)
        patient_user.patient_profile = PatientProfile(date_of_birth=date(1992, 6, 15), gender="Female", blood_group="O+", known_allergies="Penicillin", chronic_conditions="Mild asthma")
        db.add(patient_user); db.flush(); patient = patient_user.patient_profile
        db.add(Appointment(patient_id=patient.id, hospital_id=hospitals[0].id, department_id=hospitals[0].departments[2].id, preferred_date=date.today() + timedelta(days=4), preferred_time_window="10:00–12:00", reason_for_visit="Recurring skin irritation", symptoms="Itching and redness", status=AppointmentStatus.REQUESTED))
        completed = Appointment(patient_id=patient.id, hospital_id=hospitals[0].id, department_id=doctors[0].department_id, doctor_id=doctors[0].id, receptionist_id=receptionists[0].id, preferred_date=date.today() - timedelta(days=30), preferred_time_window="Morning", scheduled_start_time=datetime.now(timezone.utc) - timedelta(days=30), scheduled_end_time=datetime.now(timezone.utc) - timedelta(days=30) + timedelta(minutes=30), reason_for_visit="Seasonal fever", symptoms="Fever and fatigue", status=AppointmentStatus.COMPLETED)
        db.add(completed); db.flush()
        record = MedicalRecord(patient_id=patient.id, appointment_id=completed.id, hospital_id=hospitals[0].id, doctor_id=doctors[0].id, record_type=RecordType.CONSULTATION, chief_complaint="Fever", diagnosis="Viral upper respiratory infection", clinical_notes="Hydration and rest advised.", recommended_tests="CBC if symptoms persist", follow_up_date=date.today() - timedelta(days=23))
        db.add(record); db.flush()
        prescription = Prescription(medical_record_id=record.id, appointment_id=completed.id, patient_id=patient.id, doctor_id=doctors[0].id, general_instructions="Rest and maintain hydration", follow_up_date=record.follow_up_date)
        prescription.medicines = [PrescriptionMedicine(medicine_name="Paracetamol", dosage="500mg", frequency="Twice daily", duration="5 days", timing="After food")]
        db.add(prescription); db.commit()
        print("MedLog seed data created successfully.")
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
