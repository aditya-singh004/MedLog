from functools import lru_cache
from pathlib import Path
import secrets
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "MedLog"
    environment: str = "development"
    database_url: str = "sqlite:///./medivault.db"
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    access_token_expire_minutes: int = 480
    cookie_secure: bool = False
    algorithm: str = "HS256"
    upload_dir: Path = BASE_DIR / "uploads" / "medical_documents"
    max_upload_bytes: int = 10 * 1024 * 1024
    storage_backend: Literal["local", "s3"] = "local"
    s3_documents_bucket: str | None = None
    s3_documents_prefix: str = "medical-documents"
    aws_region: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 10
    log_level: str = "INFO"
    log_format: str = "console"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.storage_backend == "local":
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
