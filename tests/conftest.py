import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SECRET_KEY", "test-only-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.database import Base
from app.db.session import get_db
from app.main import app
from app.models import Department, DoctorProfile, Hospital, ReceptionistProfile, User


@pytest.fixture(scope="session")
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    h1 = Hospital(name="Test City Hospital", city="Jaipur", address="One Test Road", registration_number="TEST-H1")
    h2 = Hospital(name="Other Hospital", city="Delhi", address="Two Test Road", registration_number="TEST-H2")
    h1.departments = [Department(name="General Medicine")]
    h2.departments = [Department(name="General Medicine")]
    db.add_all([h1, h2]); db.flush()
    doctor_user = User(email="doctor@test.example.com", password_hash=hash_password("Doctor@123"), full_name="Test Doctor", role=UserRole.DOCTOR)
    doctor_user.doctor_profile = DoctorProfile(hospital_id=h1.id, department_id=h1.departments[0].id, specialization="General Medicine", medical_license_number="TEST-MCI-1", experience_years=5, consultation_fee=500)
    receptionist_one = User(email="rec1@test.example.com", password_hash=hash_password("Reception@123"), full_name="Reception One", role=UserRole.RECEPTIONIST)
    receptionist_one.receptionist_profile = ReceptionistProfile(hospital_id=h1.id, employee_code="TEST-R1")
    receptionist_two = User(email="rec2@test.example.com", password_hash=hash_password("Reception@123"), full_name="Reception Two", role=UserRole.RECEPTIONIST)
    receptionist_two.receptionist_profile = ReceptionistProfile(hospital_id=h2.id, employee_code="TEST-R2")
    hospital_admin = User(email="admin@test.example.com", password_hash=hash_password("Admin@123"), full_name="Hospital Admin", role=UserRole.HOSPITAL_ADMIN, hospital_id=h1.id)
    db.add_all([doctor_user, receptionist_one, receptionist_two, hospital_admin]); db.commit(); db.close()

    def override_db():
        session = TestingSession()
        try: yield session
        finally: session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        test_client.test_ids = {"hospital": h1.id, "other_hospital": h2.id, "department": h1.departments[0].id, "doctor": doctor_user.doctor_profile.id}
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def auth(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
