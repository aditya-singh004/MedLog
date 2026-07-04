# MedLog — Consent-Based Medical Records & Appointment Management System

MedLog is a production-style FastAPI application for multi-hospital appointment operations and patient-controlled longitudinal medical records. Patients can seek care at any registered hospital while retaining control over whether a doctor may view records created elsewhere.

<img width="2846" height="1626" alt="image" src="https://github.com/user-attachments/assets/bcdf6df4-2c6c-46b5-87bd-deeebc899628" />


## The problem

Medical records are commonly fragmented across providers. Moving care to a new doctor can either lose clinical context or expose more information than a patient intended. MedLog keeps records patient-centric while requiring explicit, time-limited consent before a doctor can read the full timeline.

## Key features

- Patient, receptionist, doctor, hospital-admin, and super-admin roles
- JWT bearer authentication for APIs and secure HTTP-only JWT cookies for dashboards
- Double-submit CSRF protection for browser forms and cookie-authenticated API mutations
- Hospital-scoped receptionist operations and doctor assignment checks
- Validated appointment state machine from request through consultation
- Expiring consent with approve, reject, revoke, and automatic expiry behavior
- Medical timeline, diagnosis, prescriptions, medicines, and follow-up dates
- PDF/JPG/PNG report uploads with content-type and 10MB size validation
- In-app notifications plus SMTP delivery or development console fallback
- Audit trail for login, consent, history access, prescriptions, and appointments
- PostgreSQL, SQLAlchemy 2, Alembic, Docker Compose, and pytest
- REST API with OpenAPI/Swagger plus server-rendered Bootstrap dashboards

## UI/UX highlights

- Role-based production dashboard layouts with dedicated patient, receptionist, doctor, and administrator navigation
- Responsive Bootstrap 5 interface with a desktop sidebar, mobile navigation drawer, polished forms, data tables, empty states, and status indicators
- Scan-friendly longitudinal medical-history timeline spanning hospitals, clinicians, diagnoses, tests, follow-up care, and prescriptions
- Clear consent workflow screens that distinguish pending, approved, expired, rejected, and revoked access
- Healthcare-focused blue and teal design system with Inter typography, Bootstrap Icons, accessible hierarchy, and consistent feedback states

## Architecture

```text
Browser dashboards ─┐
                    ├─> FastAPI routes ─> service-layer policy ─> SQLAlchemy ─> PostgreSQL
REST / Swagger ─────┘           │                    │
                                ├─> audit log         ├─> local document storage
                                └─> notifications     └─> SMTP or console fallback
```

Routes authenticate the caller and establish role/ownership context. Services enforce state transitions, active consent, doctor assignment, slot conflicts, notification creation, and audit writes. Database foreign keys and indexes preserve relationships and support tenant/patient queries.

## Role-based workflow

| Role | Workflow | Important boundary |
|---|---|---|
| Patient | Register, request visits, view own timeline/documents, decide consent | Cannot schedule or read another patient |
| Receptionist | Schedule, reschedule, cancel, and check in for one hospital | Cannot read medical history or prescribe |
| Doctor | View assigned visits, request consent, consult, diagnose, prescribe | Full history requires active consent |
| Hospital Admin | Operate hospital setup and dashboards | No casual medical-history access |
| Super Admin | Manage platform hospitals/staff and audit logs | Administrative role does not bypass consent |

Appointment transitions are validated in the service layer:

```text
REQUESTED → SCHEDULED → CHECKED_IN → IN_CONSULTATION → COMPLETED
    │            ├─→ RESCHEDULED ─→ CHECKED_IN
    └─→ CANCELLED├─→ CANCELLED
                 └─→ NO_SHOW
```

## Data model overview

The principal entities are `users`, role profiles, `hospitals`, `departments`, `doctor_availability`, `appointments`, `medical_records`, `prescriptions`, `prescription_medicines`, `medical_documents`, `consent_requests`, `notifications`, and `audit_logs`. Public/sensitive identifiers are UUIDs. Appointment, tenant, status, doctor, patient, and schedule fields have dedicated indexes.

A consultation record is permanently owned by the patient and references its originating doctor, hospital, and appointment. Consent controls read access; it does not move or duplicate records.

## Run with Docker (recommended)

Requirements: Docker Desktop or Docker Engine with Compose.

```bash
cp .env.example .env
```

Replace `SECRET_KEY` in `.env` with a long random value, then run:

For a local showcase with the documented demonstration accounts, set:

```env
SEED_DEMO_DATA=true
```

Keep `SEED_DEMO_DATA=false` in staging and production.

```bash
docker compose up --build
```

The web container waits for PostgreSQL, applies Alembic migrations, and starts Uvicorn. Demonstration data is loaded idempotently only when `SEED_DEMO_DATA=true`.

```bash
docker compose logs -f web
docker compose down
```

To also delete database and upload volumes:

```bash
docker compose down -v
```

## Local setup

Use Python 3.11 or newer and a PostgreSQL database. SQLite is the development fallback when `DATABASE_URL` is omitted.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                   # Windows: copy .env.example .env
alembic upgrade head
python -m app.utils.seed
uvicorn app.main:app --reload
```

For a non-Docker PostgreSQL instance, change the host in `DATABASE_URL` from `postgres` to `localhost`.

## Seed accounts

| Portal | Email | Password |
|---|---|---|
| Super Admin | `admin@medivault.com` | `Admin@123` |
| Doctor 1 | `doctor1@medivault.com` | `Doctor@123` |
| Doctor 2 | `doctor2@medivault.com` | `Doctor@123` |
| Receptionist 1 | `reception1@medivault.com` | `Reception@123` |
| Receptionist 2 | `reception2@medivault.com` | `Reception@123` |
| Patient | `patient@medivault.com` | `Patient@123` |

Seed data includes three hospitals, four departments per hospital, doctor availability, a pending appointment request, a completed consultation, and a prescription. Change all demonstration passwords outside local development.

Production deployments must set `SEED_DEMO_DATA=false`; this prevents known demonstration accounts, passwords, and sample medical records from being created in a new database.

## Important URLs

- Application: [http://localhost:8000](http://localhost:8000)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

API clients authenticate through `POST /api/auth/login`, then send `Authorization: Bearer <access_token>`. Patient self-registration is exposed at `POST /api/auth/register`; staff accounts are admin-created.

## Tests

```bash
pytest
pytest --cov=app --cov-report=term-missing
```

The integration suite uses an isolated in-memory SQLite database and covers registration, login, requesting/scheduling appointments, history denial before consent, consent approval and revoke, post-revoke denial, assigned-doctor prescribing, receptionist denial, patient ownership, and multi-hospital isolation.

## Backups and recovery

Create a timestamped PostgreSQL and medical-upload backup while Docker is running:

```powershell
.\scripts\backup.ps1
```

Backups are written below `backups/<UTC timestamp>/` with a SHA-256 manifest. The default retention window is 30 days. Keep an encrypted copy outside the computer running MedLog; a local backup alone does not protect against disk loss or ransomware.

To also upload and verify an encrypted copy in a private Amazon S3 bucket, configure the `medivault-backup` AWS CLI profile and run:

```powershell
.\scripts\backup.ps1 -S3Bucket "YOUR_PRIVATE_BUCKET_NAME" -AwsProfile "medivault-backup"
```

The off-device copy is stored under `medivault-backups/<UTC timestamp>/`. The bucket name is configuration, not a credential; AWS access keys must never be placed in this repository.

To restore a selected backup, first stop external traffic and then run the explicit destructive command:

```powershell
.\scripts\restore.ps1 -BackupDirectory .\backups\20260101T120000Z -IUnderstandThisOverwritesData
```

The restore script verifies every checksum, stops the web service, restores PostgreSQL and uploads, and restarts the application. Practice restoration on a non-production environment regularly; an untested backup is not a recovery plan.

For local daily backups, create a Windows Task Scheduler task that runs:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\path\to\MedLog\scripts\backup.ps1 -S3Bucket "YOUR_PRIVATE_BUCKET_NAME" -AwsProfile "medivault-backup"
```

On AWS, replace this local schedule with RDS automated backups and point-in-time recovery plus S3 versioning/lifecycle policies for documents.

## Monitoring and logging

```powershell
.\scripts\status.ps1
```

The status check reports container health, application liveness, database readiness, and backup freshness. Monitoring endpoints are:

- `/health/live` — process liveness without external dependencies
- `/health/ready` — application readiness including a database query
- `/health` — public service and database status

Set `LOG_FORMAT=json` in staging/production for structured logs. Request logs include a generated request ID, method, path, status, and duration, but intentionally exclude query strings, request bodies, tokens, email addresses, and medical content. Docker log rotation is capped at five 10MB files per service for local protection.

## Security design

- Passlib/bcrypt password hashing; raw passwords are never stored or logged
- Secrets and connection strings loaded from environment variables
- JWT signature and expiry validation on protected routes
- CSRF token verification on all unsafe browser form submissions and cookie-authenticated API mutations
- Reusable role dependencies plus resource ownership checks
- Hospital tenant checks on all receptionist operations
- Doctor-patient relationship, assignment, and active-consent checks
- Immediate revoke enforcement and automatic expired-consent rejection
- Audit entry for every doctor history view
- Allowlisted upload MIME types, randomized server filenames, and size limits
- Parameterized SQLAlchemy statements and Pydantic request validation
- Correct `401`, `403`, `404`, `409`, and validation responses
- SMTP notification delivery fails safely back to persistent in-app notifications without logging recipient addresses or medical message content

## Email delivery

In-app notifications always remain available. If SMTP is not configured—or a provider is temporarily unavailable—the appointment or consent workflow continues and the application writes only a content-free operational log entry.

For AWS SES over STARTTLS, configure the regional SMTP endpoint and credentials:

```env
SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-ses-smtp-username
SMTP_PASSWORD=your-ses-smtp-password
SMTP_FROM=noreply@your-verified-domain.com
SMTP_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=10
```

The sender address/domain must be verified with the SMTP provider. Never commit SMTP credentials to source control.

For internet deployment, terminate TLS at a trusted proxy, set `COOKIE_SECURE=true`, use a dedicated secrets manager, scan uploads, and restrict allowed hosts/CORS.

## Project layout

```text
app/
├── api/routes/       # REST endpoints by role
├── core/             # configuration, enums, JWT/password security
├── db/               # SQLAlchemy engine/session/base
├── models/           # relational domain model
├── schemas/          # Pydantic API contracts
├── services/         # workflow, consent, notification, audit, files
├── templates/        # Jinja2 role portals
├── static/           # Bootstrap companion styling and JavaScript
├── utils/seed.py     # idempotent demonstration data
├── web.py            # server-rendered dashboard routes
└── main.py           # application composition
alembic/               # schema migrations
tests/                 # end-to-end authorization/workflow tests
```

## Future scope

- AI-assisted patient-history summarization
- Hospital ERP integration
- SMS and WhatsApp notifications
- Encrypted S3-compatible document storage
- HL7/FHIR interoperability
- Doctor availability calendar integration

AI-assisted summarization is future scope only and is not implemented in this version.
