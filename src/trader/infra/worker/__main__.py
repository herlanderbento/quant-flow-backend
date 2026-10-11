import asyncio
import logging
import signal
import sys

from shared.infra.api.dependencies import get_encryption
from shared.infra.logging_config import configure_logging
from shared.infra.db.database import AsyncSessionLocal
from trader.infra.worker.bot_worker import BotWorker

configure_logging(default_format="json")
logger = logging.getLogger("trader.infra.worker")


def install_shutdown_handlers(worker: BotWorker) -> None:
    """SIGTERM (docker stop) and SIGINT (Ctrl+C) finish the current cycle, then exit."""
    loop = asyncio.get_running_loop()

    def request_stop(signame: str) -> None:
        logger.info("Received %s; stopping after the current cycle.", signame)
        worker.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_stop, sig.name)
        except NotImplementedError:  # Windows event loops
            signal.signal(
                sig,
                lambda signum, _frame: loop.call_soon_threadsafe(
                    request_stop, signal.Signals(signum).name
                ),
            )


async def main() -> None:
    worker = BotWorker(AsyncSessionLocal, get_encryption())
    install_shutdown_handlers(worker)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
