from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.infra.db.config import settings

DATABASE_URL = settings.DATABASE_URL

# Ensure correct async driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

def build_engine(url: str) -> AsyncEngine:
    """Engine configuration shared by the app, the worker and the integration tests."""
    return create_async_engine(
        url,
        echo=settings.SQL_ECHO,
        # Never log bound parameters: they include credentials and user data.
        hide_parameters=True,
        pool_size=20,
        max_overflow=10,
        # Survive database restarts: stale pooled connections are replaced, not used.
        pool_pre_ping=True,
    )


engine = build_engine(DATABASE_URL)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Base declarative shared by all modules
class Base(DeclarativeBase):
    pass


# Dependency injection for FastAPI
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()