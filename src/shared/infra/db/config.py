from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Environment
    ENV: str = "development"
    SQL_ECHO: bool = False

    # A worker heartbeat older than this is reported as stale.
    WORKER_STALE_SECONDS: int = 60

    # Operational alerts (always logged; the webhook is optional and off by default)
    ALERT_WEBHOOK_URL: str | None = None
    ALERT_COOLDOWN_SECONDS: int = 900
    ALERT_CONSECUTIVE_FAILURES: int = 6
    ALERT_MARKET_DATA_STALE_SECONDS: int = 300
    # Ledger audit every N worker cycles (30 x 10 s = 5 min)
    AUDIT_EVERY_CYCLES: int = 30

    # Machine learning. The model is loaded once at worker start-up (never trained here).
    ML_MODEL_PATH: str | None = None
    # Record the model's opinion next to every bot's real decision (no influence on trading).
    ML_SHADOW_ENABLED: bool = True
    # Let bots with strategy_type=ML_SIGNAL trade on the model (paper/testnet only).
    ML_TRADING_ENABLED: bool = False

    # Trading mode. 'paper' (default) never sends orders to any exchange.
    # 'testnet' only accepts testnet credentials. 'live' also requires
    # LIVE_TRADING_ENABLED=true and moves real money.
    TRADING_MODE: Literal["paper", "testnet", "live"] = "paper"
    # Comma-separated symbols the gateway may size and order (all modes).
    TRADABLE_SYMBOLS: str = "BTC/USDT,ETH/USDT"
    LIVE_TRADING_ENABLED: bool = False

    # Paper trading simulation costs
    PAPER_TAKER_FEE_RATE: float = 0.001
    PAPER_SLIPPAGE_BPS: float = 5.0

    # Risk limits (checked before every new entry; exits are never blocked)
    TRADING_HALTED: bool = False
    MAX_DAILY_LOSS_PCT: float = 3.0
    MAX_DRAWDOWN_PCT: float = 10.0
    MAX_USER_EXPOSURE_USDT: float = 1000.0
    MAX_STOP_LOSS_PCT: float = 10.0

    # Symmetric encryption key (Fernet) for exchange API credentials
    # Generate with: cryptography.fernet.Fernet.generate_key()
    ENCRYPTION_KEY: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # renewed through POST /auth/refresh
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookie
    COOKIE_SECURE: bool = True  # set false only for plain-http local development
    COOKIE_HTTPONLY: bool = True
    COOKIE_SAMESITE: str = "lax"
    ACCESS_TOKEN_COOKIE: str = "access_token"
    REFRESH_TOKEN_COOKIE: str = "refresh_token"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def tradable_symbols(self) -> frozenset[str]:
        return frozenset(s.strip().upper() for s in self.TRADABLE_SYMBOLS.split(",") if s.strip())


settings = Settings()

MIN_JWT_SECRET_BYTES = 32  # RFC 7518 section 3.2 for HS256
if len(settings.JWT_SECRET_KEY.encode()) < MIN_JWT_SECRET_BYTES:
    import logging

    logging.getLogger(__name__).warning(
        "JWT_SECRET_KEY is shorter than %d bytes; generate a longer random key "
        "(e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\").",
        MIN_JWT_SECRET_BYTES,
    )
