from pathlib import Path
import re

from app.web import templates


def test_all_jinja_templates_compile():
    root = Path("app/templates")
    for template_path in root.rglob("*.html"):
        templates.env.get_template(template_path.relative_to(root).as_posix())


def login_cookie(client, email: str, password: str):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_public_and_role_pages_render(client):
    for path in ("/", "/login", "/register"):
        response = client.get(path)
        assert response.status_code == 200
        assert "MedLog" in response.text

    registration = client.post("/api/auth/register", json={"email": "ui.patient@example.com", "password": "Patient@123", "full_name": "UI Patient"})
    assert registration.status_code == 201
    login_cookie(client, "ui.patient@example.com", "Patient@123")
    for path in ("/patient/dashboard", "/patient/hospitals", "/patient/appointments/request", "/patient/appointments", "/patient/medical-history", "/patient/documents", "/patient/consents", "/patient/notifications"):
        assert client.get(path).status_code == 200

    client.cookies.clear()
    login_cookie(client, "rec1@test.example.com", "Reception@123")
    for path in ("/receptionist/dashboard", "/receptionist/appointments/requests", "/receptionist/queue", "/receptionist/notifications"):
        assert client.get(path).status_code == 200

    client.cookies.clear()
    login_cookie(client, "doctor@test.example.com", "Doctor@123")
    for path in ("/doctor/dashboard", "/doctor/appointments", "/doctor/notifications"):
        assert client.get(path).status_code == 200

    client.cookies.clear()
    login_cookie(client, "admin@test.example.com", "Admin@123")
    for path in ("/admin/dashboard", "/admin/hospitals", "/admin/departments", "/admin/doctors", "/admin/receptionists"):
        assert client.get(path).status_code == 200
    assert "Go to dashboard" in client.get("/").text


def test_web_forms_require_valid_csrf_token(client):
    client.cookies.clear()
    page = client.get("/login")
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)

    missing = client.post("/login", data={"email": "doctor@test.example.com", "password": "Doctor@123"}, follow_redirects=False)
    assert missing.status_code == 403

    invalid = client.post("/login", data={"email": "doctor@test.example.com", "password": "Doctor@123", "csrf_token": "wrong-token"}, follow_redirects=False)
    assert invalid.status_code == 403

    valid = client.post("/login", data={"email": "doctor@test.example.com", "password": "Doctor@123", "csrf_token": token}, follow_redirects=False)
    assert valid.status_code == 303


def test_cookie_authenticated_api_requires_csrf_header(client):
    client.cookies.clear()
    login_cookie(client, "ui.patient@example.com", "Patient@123")
    token = client.cookies.get("csrf_token")

    blocked = client.post("/api/patient/notifications/not-found/read")
    assert blocked.status_code == 403

    protected = client.post("/api/patient/notifications/not-found/read", headers={"X-CSRF-Token": token})
    assert protected.status_code == 404
