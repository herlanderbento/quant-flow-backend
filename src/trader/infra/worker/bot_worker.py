import asyncio
import logging
from datetime import timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from account.infra.db.credential_postgres_repository import CredentialPostgresRepository
from shared.application.cryptography import IEncryption
from trader.application.order_sizing import calculate_order_quantity
from trader.application.risk_management import evaluate_exit
from trader.domain.bot import Bot
from trader.domain.interface.strategy_interface import TradeSignal
from trader.domain.strategies.strategy_factory import StrategyFactory
from trader.domain.trade import Trade, TradeCreateCommand, TRADE_STATUS_OPEN
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.infra.db.trade_postgres_repository import TradePostgresRepository
from trader.infra.gateway.bybit_gateway import BybitGateway


logger = logging.getLogger(__name__)

ACTIONABLE_SIGNALS = frozenset({TradeSignal.BUY, TradeSignal.SELL})
WORKER_CYCLE_SECONDS = 10


class BotWorker:

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        encryption_service: IEncryption,
    ):

        self.session_factory = session_factory
        self.encryption_service = encryption_service
        self.is_running = False

    async def run(self) -> None:
        self.is_running = True
        logger.info("BotWorker started.")

        while self.is_running:
            try:
                async with self.session_factory() as session:
                    bot_repo = BotPostgresRepository(session)
                    active_bots = await bot_repo.find_active()

                    if active_bots:
                        await asyncio.gather(
                            *[self._process_bot(bot) for bot in active_bots]
                        )

            except Exception as e:
                logger.error("Critical error in worker loop: %s", e)
            await asyncio.sleep(WORKER_CYCLE_SECONDS)

    def stop(self) -> None:
        self.is_running = False

    async def _process_bot(self, bot: Bot) -> None:
        gateway = None
        async with self.session_factory() as session:

            try:
                cred_repo = CredentialPostgresRepository(session)
                creds = await cred_repo.find_by_id(bot.credential_id.value)
                if not creds:
                    logger.error(
                        "Credential not found for bot %s (%s)", bot.name, bot.id
                    )
                    return

                if not creds.is_active:
                    logger.warning(
                        "Credential inactive for bot %s (%s)", bot.name, bot.id
                    )
                    return
                api_secret = self.encryption_service.decrypt(creds.api_secret)
                gateway = BybitGateway(
                    creds.api_key, api_secret, is_testnet=creds.is_testnet
                )

                trade_repo = TradePostgresRepository(session)
                open_trades = await trade_repo.find_open_by_bot_id(bot.id)
                market_data = await gateway.get_market_snapshot(bot.symbol)

                if open_trades:
                    closed = await self._maybe_close_position(
                        session,
                        gateway,
                        bot,
                        trade_repo,
                        open_trades[0],
                        market_data.current_price,
                    )

                    if closed:
                        await session.commit()

                    return

                strategy = StrategyFactory.get_strategy(bot.strategy_type)
                signal = await strategy.analyze(market_data)

                if signal not in ACTIONABLE_SIGNALS:
                    return

                quantity = calculate_order_quantity(
                    bot.allocated_capital, market_data.current_price
                )
                order = await gateway.place_market_order(
                    bot.symbol, signal.value, quantity
                )

                trade = Trade.create(
                    TradeCreateCommand(
                        bot_id=bot.id,
                        ai_prediction_id=None,
                        symbol=bot.symbol,
                        side=signal.value,
                        status=TRADE_STATUS_OPEN,
                        price_executed=order.price,
                        quantity=order.quantity,
                        exchange_order_id=order.order_id,
                    )
                )

                await trade_repo.insert(trade)
                await session.commit()

                logger.info(
                    "Order executed for bot %s: %s %s %s @ %s",
                    bot.name,
                    signal.value,
                    order.quantity,
                    bot.symbol,
                    order.price,
                )

            except Exception as e:
                await session.rollback()
                logger.error("Error processing bot %s (%s): %s", bot.name, bot.id, e)

            finally:
                if gateway is not None:

                    await gateway.close()

    async def _maybe_close_position(
        self,
        session,
        gateway: BybitGateway,
        bot: Bot,
        trade_repo: TradePostgresRepository,
        trade: Trade,
        current_price: float,
    ) -> bool:

        decision = evaluate_exit(
            side=trade.side,
            entry_price=trade.price_executed,
            current_price=current_price,
            stop_loss_pct=bot.stop_loss_pct,
            take_profit_pct=bot.take_profit_pct,
        )

        if not decision.should_exit:

            return False

        close_side = "SELL" if trade.side == "BUY" else "BUY"

        order = await gateway.place_market_order(bot.symbol, close_side, trade.quantity)

        from datetime import datetime

        trade.close_with_pnl(
            exit_price=order.price,
            closed_at=datetime.now(timezone.utc),
        )

        await trade_repo.update(trade)

        logger.info(
            "Position closed for bot %s (%s): %s",
            bot.name,
            decision.reason,
            order.order_id,
        )

        return True
