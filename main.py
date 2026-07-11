import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from contextlib import asynccontextmanager
from fastapi import FastAPI

from shared.infra.db.config import settings
from shared.infra.db.database import engine
from shared.infra.api.exception_handlers import register_exception_handlers
from shared.infra.db.metadata import target_metadata
from account.infra.api.user.auth_controller import router as auth_router
from account.infra.api.user.user_controller import router as user_router
from account.infra.api.credential.credential_controller import router as credential_router
from trader.infra.api.bot.bot_controller import router as bot_router
from trader.infra.api.trade.trade_controller import router as trade_router
from trader.infra.api.backtest.backtest_controller import router as backtest_router
from wallet.infra.api.wallet.wallet_controller import router as wallet_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(target_metadata.create_all)
        print("🚀 QuantFlow database synchronized!")
    yield
    await engine.dispose()


app = FastAPI(title="QuantFlow - MVP", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(credential_router)
app.include_router(bot_router)
app.include_router(trade_router)
app.include_router(backtest_router)
app.include_router(wallet_router)


@app.get("/")
def read_root():
    return {"status": "QuantFlow backend running successfully in Docker"}