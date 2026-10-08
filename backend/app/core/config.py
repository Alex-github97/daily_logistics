from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    PROJECT_NAME: str = "Daily Logistics"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str = "postgresql+asyncpg://dl_user:dl_pass@localhost:5434/daily_logistics"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CORS_ORIGINS: List[str] = ["http://localhost:5180", "http://127.0.0.1:5180"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    SAP_HOST: str = ""
    SAP_PORT: int = 443
    SAP_CLIENT: str = "100"
    SAP_USER: str = ""
    SAP_PASSWORD: str = ""
    SAP_ENABLED: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
