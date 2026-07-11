import asyncio
import logging

from shared.infra.api.dependencies import get_encryption
from shared.infra.db.database import AsyncSessionLocal
from trader.infra.worker.bot_worker import BotWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    worker = BotWorker(AsyncSessionLocal, get_encryption())
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
