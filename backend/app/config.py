import os
from dataclasses import dataclass


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    ENVIRONMENT: str = _env("ENVIRONMENT", "development")
    FRONTEND_URL: str = _env("FRONTEND_URL", "http://127.0.0.1:5173")
    ALLOWED_ORIGINS: str = _env("ALLOWED_ORIGINS", "http://127.0.0.1:5173")

    OPENAI_API_KEY: str = _env("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-4.1-mini")
    OPENAI_REASONING_MODEL: str = _env("OPENAI_REASONING_MODEL", "gpt-4.1-mini")
    OPENAI_EMBEDDING_MODEL: str = _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    DATABASE_URL: str = _env("DATABASE_URL", "")
    TOKEN_ENCRYPTION_KEY: str = _env("TOKEN_ENCRYPTION_KEY", "")

    GOOGLE_CLIENT_ID: str = _env("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = _env("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = _env("GOOGLE_REDIRECT_URI", "")

    SUPABASE_URL: str = _env("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = _env("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_STORAGE_BUCKET: str = _env("SUPABASE_STORAGE_BUCKET", "email-attachments")

    SENTRY_DSN: str = _env("SENTRY_DSN", "")

    THRESH_HIGH: float = float(_env("THRESH_HIGH", "0.80"))
    THRESH_MED: float = float(_env("THRESH_MED", "0.55"))


settings = Settings()
