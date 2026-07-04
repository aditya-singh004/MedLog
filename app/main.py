from contextlib import asynccontextmanager
from pathlib import Path
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import admin, auth, doctor, patient, receptionist
from app.core.config import settings
from app.core.csrf import CSRF_COOKIE_NAME, new_csrf_token, validate_api_csrf, validate_web_csrf
from app.core.logging import configure_logging
from app.db.database import Base
from app.db.session import engine, get_db
from app.web import router as web_router


configure_logging()
logger = logging.getLogger("medivault.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.storage_backend == "local":
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="MedLog — Consent-Based Medical Records & Appointment Management System",
    description="Multi-hospital appointment and consent-governed longitudinal medical records platform.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    token = request.cookies.get(CSRF_COOKIE_NAME) or new_csrf_token()
    request.state.csrf_token = token
    response = await call_next(request)
    if not request.cookies.get(CSRF_COOKIE_NAME):
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=8 * 60 * 60,
            path="/",
        )
    return response


@app.middleware("http")
async def safe_request_logging(request: Request, call_next):
    request_id = str(uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled request error",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
api_csrf = [Depends(validate_api_csrf)]
app.include_router(auth.router, dependencies=api_csrf)
app.include_router(patient.router, dependencies=api_csrf)
app.include_router(receptionist.router, dependencies=api_csrf)
app.include_router(doctor.router, dependencies=api_csrf)
app.include_router(admin.router, dependencies=api_csrf)
app.include_router(web_router, dependencies=[Depends(validate_web_csrf)])


@app.get("/health", tags=["System"])
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "healthy", "service": "medivault", "database": "connected"}


@app.get("/health/live", tags=["System"], include_in_schema=False)
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["System"], include_in_schema=False)
def readiness(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ready", "database": "connected"}
