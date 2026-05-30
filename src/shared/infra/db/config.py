from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Docker injects the URL; when running locally, uses the localhost fallback
    DATABASE_URL: str = "postgresql+asyncpg://quantflow_admin:quantflow_password_2026@localhost:6000/quantflow_db"
    
    # Symmetric encryption key (Fernet) for Binance API credentials
    # Generate with: cryptography.fernet.Fernet.generate_key()
    ENCRYPTION_KEY: str = "3zR8W6_pL89VfXvZ2k8hb9J9-V9K6N7B3vC5xY8z1A4=" 

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()