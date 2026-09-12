from pathlib import Path
from pydantic import Field, AliasChoices, model_validator
from typing import Literal
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load configuration from environment variables (and optional .env file)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    SESSION_MAX_AGE: int = Field(default=60 * 60 * 24, ge=60, le=60 * 60 * 24 * 30)
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"
    LOGIN_RATE_LIMIT: int = Field(default=30, ge=1)
    REGISTER_RATE_LIMIT: int = Field(default=10, ge=1)
    REQUEST_RATE_LIMIT: int = Field(default=30, ge=1)
    MESSAGE_RATE_LIMIT: int = Field(default=120, ge=1)
    WS_RATE_LIMIT: int = Field(default=60, ge=1)
    MAX_PENDING_GUIDANCE_REQUESTS: int = Field(default=5, ge=1, le=100)
    REQUEST_REJECTION_COOLDOWN_DAYS: int = Field(default=30, ge=1, le=365)
    VERIFICATION_STORAGE_DIR: str = Field(default=str(Path(__file__).resolve().parents[1] / "private_uploads"), validation_alias=AliasChoices("UPLOAD_DIRECTORY", "VERIFICATION_STORAGE_DIR"))
    SESSION_HTTPS_ONLY: bool = False
    SESSION_SAME_SITE: Literal["lax", "strict", "none"] = "lax"
    FRONTEND_ORIGINS: str = Field(default="http://localhost:5500,http://127.0.0.1:5500", validation_alias=AliasChoices("FRONTEND_ORIGIN", "FRONTEND_ORIGINS"))

    @model_validator(mode="after")
    def secure_configuration(self):
        if not self.cors_origins:
            raise ValueError("Configure at least one frontend origin.")
        for origin in self.cors_origins:
            url = urlsplit(origin)
            if url.scheme not in ("http", "https") or not url.netloc or url.path or url.query or url.fragment or "*" in origin or url.username:
                raise ValueError("Frontend origins must be explicit HTTP(S) origins without paths or wildcards.")
        if self.SESSION_SAME_SITE == "none" and not self.SESSION_HTTPS_ONLY:
            raise ValueError("SameSite=None requires secure cookies.")
        if self.ENVIRONMENT == "production":
            if len(self.SECRET_KEY) < 32 or any(word in self.SECRET_KEY.lower() for word in ("replace", "change-me", "test-secret")):
                raise ValueError("Production requires a strong secret key of at least 32 characters.")
            if not self.SESSION_HTTPS_ONLY or any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("Production requires HTTPS origins and secure session cookies.")
            if "*" in self.ALLOWED_HOSTS or not self.ALLOWED_HOSTS.strip():
                raise ValueError("Production requires explicit allowed hosts.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.FRONTEND_ORIGINS.split(",") if origin.strip()]


settings = Settings()
