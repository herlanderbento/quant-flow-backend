import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from contextlib import asynccontextmanager
from fastapi import FastAPI

from shared.infra.db.database import engine
from shared.infra.api.exception_handlers import register_exception_handlers
from account.infra.api.user.auth_controller import router as auth_router
from account.infra.api.user.user_controller import router as user_router
from account.infra.api.credential.credential_controller import router as credential_router
from trader.infra.api.bot.bot_controller import router as bot_router
from trader.infra.api.trade.trade_controller import router as trade_router
from trader.infra.api.backtest.backtest_controller import router as backtest_router
from wallet.infra.api.wallet.wallet_controller import router as wallet_router
from trader.infra.api.ops.ops_controller import router as ops_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is owned by Alembic (`alembic upgrade head` runs before the server starts);
    # creating tables from the models here would hide a missing migration.
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
app.include_router(ops_router)


@app.get("/")
def read_root():
    return {"status": "QuantFlow backend running successfully in Docker"}