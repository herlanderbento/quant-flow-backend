import sys
from pathlib import Path

# Allow `shared.*` imports when running from repo root (Docker sets PYTHONPATH=/app/src)
_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.infra.db.database import engine, Base
import shared.infra.db.models_registry  # noqa: F401 — registers ORM models on Base.metadata

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables automatically in Postgres if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("🚀 QuantFlow database synchronized and tables created!")
    yield
    await engine.dispose()


app = FastAPI(title="QuantFlow - MVP", lifespan=lifespan)


@app.get("/")
def read_root():
    return {"status": "QuantFlow backend running successfully in Docker"}
