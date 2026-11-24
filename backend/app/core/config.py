"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Excel Auto Grader API"
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "dev-secret-change-in-production-64-chars-minimum-0123456789abcdef"
    TOKEN_ENCRYPTION_KEY: str = ""  # Fernet base64 key; auto-derived from APP_SECRET_KEY in dev if empty

    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000"

    DATABASE_URL: str = "sqlite:///./excel_auto_grader_dev.db"
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    SUPABASE_STORAGE_BUCKET: str = "excel-auto-grader"

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/google-accounts/callback"

    LIBREOFFICE_BIN: str = "soffice"
    EXCEL_MAX_FILE_SIZE_MB: int = 50
    EXCEL_RECALC_TIMEOUT_SECONDS: int = 30
    LOCAL_STORAGE_DIR: str = "./storage_data"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = {o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()}
        if self.FRONTEND_URL.strip():
            origins.add(self.FRONTEND_URL.strip().rstrip("/"))
        return sorted(origins)

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def supabase_configured(self) -> bool:
        return bool(
            self.SUPABASE_URL
            and (self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_ANON_KEY or self.SUPABASE_JWT_SECRET)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
