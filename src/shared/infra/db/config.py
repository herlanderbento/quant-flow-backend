from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Docker injects the URL; when running locally, uses the localhost fallback
    DATABASE_URL: str = "postgresql+asyncpg://quantflow_admin:quantflow_password_2026@localhost:6000/quantflow_db"
    
    # Symmetric encryption key (Fernet) for Binance API credentials
    # Generate with: cryptography.fernet.Fernet.generate_key()
    ENCRYPTION_KEY: str = "3zR8W6_pL89VfXvZ2k8hb9J9-V9K6N7B3vC5xY8z1A4="

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    COOKIE_SECURE: bool = False
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax"
    ACCESS_TOKEN_COOKIE: str = "access_token"
    REFRESH_TOKEN_COOKIE: str = "refresh_token"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()