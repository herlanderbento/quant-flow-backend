import sys
from pathlib import Path

# Allow `shared.*` imports when running from repo root (Docker sets PYTHONPATH=/app/src)
_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from contextlib import asynccontextmanager

from fastapi import FastAPI

from account.infra.api.user.auth_controller import router as auth_router
from account.infra.api.user.user_controller import router as user_router
from account.infra.db.sql_models import Base as AccountBase
from shared.infra.api.exception_handlers import register_exception_handlers
from shared.infra.db.database import engine, Base
from trader.infra.db.sql_models import Base as TraderBase
from wallet.infra.db.sql_models import Base as WalletBase

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables automatically in Postgres if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(AccountBase.metadata.create_all)
        await conn.run_sync(TraderBase.metadata.create_all)
        await conn.run_sync(WalletBase.metadata.create_all)
    print("🚀 QuantFlow database synchronized and tables created!")
    yield
    await engine.dispose()


app = FastAPI(title="QuantFlow - MVP", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(user_router)


@app.get("/")
def read_root():
    return {"status": "QuantFlow backend running successfully in Docker"}
