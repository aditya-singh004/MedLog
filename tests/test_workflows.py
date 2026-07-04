from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import auth


@pytest.fixture(scope="module")
def flow(client):
    out = {}
    registration = client.post("/api/auth/register", json={"email": "patient1@test.example.com", "password": "Patient@123", "full_name": "Patient One", "date_of_birth": "1990-01-01", "gender": "Female"})
    out["registration"] = registration
    client.post("/api/auth/register", json={"email": "patient2@test.example.com", "password": "Patient@123", "full_name": "Patient Two"})
    patient = auth(client, "patient1@test.example.com", "Patient@123")
    patient_two = auth(client, "patient2@test.example.com", "Patient@123")
    receptionist = auth(client, "rec1@test.example.com", "Reception@123")
    other_receptionist = auth(client, "rec2@test.example.com", "Reception@123")
    doctor = auth(client, "doctor@test.example.com", "Doctor@123")
    out["login"] = client.get("/api/auth/me", headers=patient)

    requested = client.post("/api/patient/appointments/request", headers=patient, json={
        "hospital_id": client.test_ids["hospital"], "department_id": client.test_ids["department"],
        "preferred_date": str(date.today() + timedelta(days=2)), "preferred_time_window": "10:00-12:00",
        "reason_for_visit": "Persistent headache", "symptoms": "Headache and nausea", "notes": "First visit",
    })
    out["requested"] = requested
    appointment_id = requested.json()["id"]
    start = datetime.now(timezone.utc) + timedelta(days=2)
    schedule_body = {"doctor_id": client.test_ids["doctor"], "scheduled_start_time": start.isoformat(), "scheduled_end_time": (start + timedelta(minutes=30)).isoformat()}
    out["other_hospital_schedule"] = client.post(f"/api/receptionist/appointments/{appointment_id}/schedule", headers=other_receptionist, json=schedule_body)
    out["scheduled"] = client.post(f"/api/receptionist/appointments/{appointment_id}/schedule", headers=receptionist, json=schedule_body)
    patient_id = requested.json()["patient_id"]

    out["history_without_consent"] = client.get(f"/api/doctor/patients/{patient_id}/medical-history", headers=doctor)
    consent = client.post(f"/api/doctor/patients/{patient_id}/consent-request", headers=doctor, json={"requested_reason": "Review prior care", "appointment_id": appointment_id})
    out["consent_requested"] = consent
    consent_id = consent.json()["id"]
    out["consent_approved"] = client.post(f"/api/patient/consent-requests/{consent_id}/approve", headers=patient, json={"duration_hours": 24})
    out["history_with_consent"] = client.get(f"/api/doctor/patients/{patient_id}/medical-history", headers=doctor)
    out["consent_revoked"] = client.post(f"/api/patient/consent-requests/{consent_id}/revoke", headers=patient)
    out["history_after_revoke"] = client.get(f"/api/doctor/patients/{patient_id}/medical-history", headers=doctor)

    out["checked_in"] = client.post(f"/api/receptionist/appointments/{appointment_id}/check-in", headers=receptionist)
    out["started"] = client.post(f"/api/doctor/appointments/{appointment_id}/start", headers=doctor)
    prescription_body = {"diagnosis": "Tension headache", "clinical_notes": "No neurological deficit", "recommended_tests": "None presently", "general_instructions": "Hydrate and rest", "medicines": [{"medicine_name": "Paracetamol", "dosage": "500mg", "frequency": "Twice daily", "duration": "3 days", "timing": "After food"}]}
    out["receptionist_prescribe"] = client.post(f"/api/doctor/appointments/{appointment_id}/prescription", headers=receptionist, json=prescription_body)
    out["prescribed"] = client.post(f"/api/doctor/appointments/{appointment_id}/prescription", headers=doctor, json=prescription_body)
    out["other_patient_appointment"] = client.get(f"/api/patient/appointments/{appointment_id}", headers=patient_two)
    out["patient_history"] = client.get("/api/patient/medical-history", headers=patient)
    return out


def test_patient_registration(flow):
    assert flow["registration"].status_code == 201
    assert flow["registration"].json()["role"] == "PATIENT"


def test_login(flow):
    assert flow["login"].status_code == 200
    assert flow["login"].json()["email"] == "patient1@test.example.com"


def test_patient_appointment_request(flow):
    assert flow["requested"].status_code == 201
    assert flow["requested"].json()["status"] == "REQUESTED"


def test_receptionist_scheduling(flow):
    assert flow["scheduled"].status_code == 200
    assert flow["scheduled"].json()["status"] == "SCHEDULED"


def test_doctor_cannot_access_history_without_consent(flow):
    assert flow["history_without_consent"].status_code == 403


def test_doctor_requests_consent(flow):
    assert flow["consent_requested"].status_code == 201
    assert flow["consent_requested"].json()["status"] == "PENDING"


def test_patient_approves_consent(flow):
    assert flow["consent_approved"].status_code == 200
    assert flow["consent_approved"].json()["status"] == "APPROVED"


def test_doctor_accesses_history_after_consent(flow):
    assert flow["history_with_consent"].status_code == 200


def test_patient_revokes_consent(flow):
    assert flow["consent_revoked"].status_code == 200
    assert flow["consent_revoked"].json()["status"] == "REVOKED"


def test_doctor_blocked_after_revoke(flow):
    assert flow["history_after_revoke"].status_code == 403


def test_prescription_creation_by_assigned_doctor(flow):
    assert flow["prescribed"].status_code == 201
    assert flow["prescribed"].json()["status"] == "COMPLETED"
    assert len(flow["patient_history"].json()) == 1


def test_receptionist_blocked_from_prescription(flow):
    assert flow["receptionist_prescribe"].status_code == 403


def test_patient_blocked_from_another_patients_records(flow):
    assert flow["other_patient_appointment"].status_code == 404


def test_multi_hospital_receptionist_isolation(flow):
    assert flow["other_hospital_schedule"].status_code == 404


def test_hospital_admin_isolation(client):
    hospital_admin = auth(client, "admin@test.example.com", "Admin@123")
    response = client.post(f"/api/admin/hospitals/{client.test_ids['other_hospital']}/departments", headers=hospital_admin, json={"name": "Forbidden Department"})
    assert response.status_code == 403
