import asyncio
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from account.infra.db.credential_postgres_repository import CredentialPostgresRepository
from account.domain.credential import Credential
from shared.application.cryptography import IEncryption
from shared.application.log_context import log_context
from shared.infra.db.config import settings
from trader.application.alerts import SEVERITY_CRITICAL, SEVERITY_ERROR, AlertService
from trader.application.bot_cycle import DEFAULT_PENDING_GRACE, BotCycle, CycleOutcome
from trader.application.risk_guard import RiskGuard, RiskLimits
from trader.application.worker_metrics import WorkerMetrics
from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from ml.inference.shadow import ShadowRecordingStrategy
from ml.inference.strategy import ML_STRATEGY_NAME, MLDecision, MLSignalStrategy
from ml.models.artifact import ModelPredictor
from trader.domain.bot import Bot
from trader.domain.interface.strategy_interface import IBotStrategy
from trader.domain.interface.exchange_gateway_interface import IExchangeGateway
from trader.domain.strategies.strategy_factory import StrategyFactory
from trader.infra.alerts.webhook_sink import WebhookAlertSink
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.infra.db.ledger_audit import audit_trade_ledger
from trader.infra.db.ml_prediction_log_repository import (
    MlPredictionLogRepository,
    PredictionLogEntry,
)
from trader.infra.db.trade_postgres_repository import TradePostgresRepository
from trader.infra.db.worker_status_postgres_repository import WorkerStatusPostgresRepository
from trader.infra.gateway.bybit_gateway import BybitGateway
from trader.infra.gateway.gateway_factory import create_trading_gateway
from trader.infra.gateway.paper_gateway import PaperExchangeGateway


logger = logging.getLogger(__name__)

WORKER_CYCLE_SECONDS = 10


# Outcomes that need a human: the bot refuses to act until someone looks.
ALERTING_OUTCOMES = {
    CycleOutcome.POSITION_MISMATCH: SEVERITY_CRITICAL,
    CycleOutcome.INCONSISTENT: SEVERITY_CRITICAL,
    CycleOutcome.EXIT_REJECTED: SEVERITY_CRITICAL,
    CycleOutcome.EXIT_BELOW_MINIMUM: SEVERITY_CRITICAL,
    CycleOutcome.RECONCILE_FAILED: SEVERITY_ERROR,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_predictor() -> tuple[ModelPredictor | None, str | None]:
    """Load the configured model once; any problem disables ML (never trading on it)."""
    if not settings.ML_MODEL_PATH:
        return None, "ML_MODEL_PATH not configured"
    try:
        predictor = ModelPredictor.load(
            settings.ML_MODEL_PATH, FEATURE_SCHEMA_VERSION, FEATURE_NAMES
        )
    except Exception as error:
        logger.exception("ML model could not be loaded; ML disabled")
        return None, f"model failed to load: {type(error).__name__}: {error}"[:300]
    logger.info("ML model loaded", extra={"model_version": predictor.model_version})
    return predictor, None


def _log_entry(bot: Bot, mode: str, candle, decision: MLDecision, used, predictor) -> PredictionLogEntry:
    return PredictionLogEntry(
        bot_id=bot.id.value,
        symbol=bot.symbol,
        mode=mode,
        model_version=predictor.model_version,
        market_candle_close=candle,
        feature_candle_close=decision.feature_candle_close,
        probability=decision.probability,
        decision=decision.signal.value,
        strategy_signal=used.value if used is not None else None,
        reason=decision.reason,
        buy_threshold=predictor.buy_threshold,
        sell_threshold=predictor.sell_threshold,
        features=decision.features,
    )


def _default_alerts() -> AlertService:
    sinks = [WebhookAlertSink(settings.ALERT_WEBHOOK_URL)] if settings.ALERT_WEBHOOK_URL else []
    return AlertService(sinks, cooldown=timedelta(seconds=settings.ALERT_COOLDOWN_SECONDS))


def _risk_limits() -> RiskLimits:
    return RiskLimits(
        trading_halted=settings.TRADING_HALTED,
        max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
        max_drawdown_pct=settings.MAX_DRAWDOWN_PCT,
        max_user_exposure=settings.MAX_USER_EXPOSURE_USDT,
    )


class BotWorker:

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        encryption_service: IEncryption,
        alerts: AlertService | None = None,
    ):

        self.session_factory = session_factory
        self.encryption_service = encryption_service
        self.is_running = False
        self._stop_requested = asyncio.Event()
        self.alerts = alerts or _default_alerts()
        self.predictor, self.predictor_error = load_predictor()
        self._last_logged_candle: dict[tuple, object] = {}
        hostname = socket.gethostname()
        self.metrics = WorkerMetrics(
            worker_id=f"{hostname}-{os.getpid()}-{uuid4().hex[:6]}",
            trading_mode=settings.TRADING_MODE,
            hostname=hostname,
            started_at=_utcnow(),
        )
        # Gateways are reused across cycles: markets load once, rate limiting
        # applies per client, and the paper ledger survives between cycles.
        self._gateways: dict[str, IExchangeGateway] = {}

    async def run(self) -> None:
        self.is_running = True
        self._stop_requested.clear()
        logger.info("BotWorker started in TRADING_MODE=%s.", settings.TRADING_MODE)

        while self.is_running:
            await self.run_cycle()
            await self._sleep_until_next_cycle()

        self.metrics.stopped_at = _utcnow()
        await self._persist_status()
        await self.close_gateways()
        logger.info("BotWorker stopped.")

    async def run_cycle(self) -> None:
        with log_context(cycle_id=uuid4().hex[:12], worker_id=self.metrics.worker_id):
            bots: list[Bot] = []
            try:
                async with self.session_factory() as session:
                    bots = await BotPostgresRepository(session).find_needing_processing()
            except Exception as error:
                self.metrics.cycle_started(_utcnow(), bots=0)
                self.metrics.record_error(error)
                logger.exception("Critical error in worker loop")
            else:
                self.metrics.cycle_started(_utcnow(), bots=len(bots))
                if bots:
                    await asyncio.gather(*[self._process_bot(bot) for bot in bots])
            self.metrics.cycle_finished(_utcnow())
            if self.metrics.cycles_total % settings.AUDIT_EVERY_CYCLES == 0:
                await self.run_audit()
            await self._raise_cycle_alerts(bots)
            await self._persist_status()

    async def _raise_cycle_alerts(self, bots: list[Bot]) -> None:
        if self.metrics.consecutive_failures >= settings.ALERT_CONSECUTIVE_FAILURES:
            await self.alerts.alert(
                "worker.consecutive_failures", SEVERITY_CRITICAL,
                f"{self.metrics.consecutive_failures} consecutive failing cycles: "
                f"{self.metrics.last_error}",
                worker_id=self.metrics.worker_id,
            )
        if bots:
            reference = self.metrics.last_market_data_at or self.metrics.started_at
            age = (_utcnow() - reference).total_seconds()
            if age > settings.ALERT_MARKET_DATA_STALE_SECONDS:
                await self.alerts.alert(
                    "market_data.stale", SEVERITY_CRITICAL,
                    f"No successful market data for {age:.0f}s",
                    worker_id=self.metrics.worker_id, age_seconds=round(age),
                )

    async def run_audit(self) -> None:
        paper_fills = []
        for gateway in self._gateways.values():
            if isinstance(gateway, PaperExchangeGateway):
                paper_fills += gateway.simulated_fills()
        try:
            async with self.session_factory() as session:
                result = await audit_trade_ledger(
                    session,
                    now=_utcnow(),
                    stuck_after=DEFAULT_PENDING_GRACE * 2,
                    paper_fills=paper_fills,
                )
        except Exception as error:
            self.metrics.record_error(error)
            logger.exception("Ledger audit failed")
            return
        self.metrics.last_audit_at = _utcnow()
        self.metrics.audit_issues = len(result.issues)
        self.metrics.audit_details = result.as_details()
        if result.ok:
            logger.info("Ledger audit passed", extra={"audit_issues": 0})
        else:
            await self.alerts.alert(
                "ledger.audit", SEVERITY_CRITICAL,
                f"{len(result.issues)} ledger issue(s): {result.issues[:3]}",
                worker_id=self.metrics.worker_id, issues=len(result.issues),
            )

    async def _persist_status(self) -> None:
        try:
            async with self.session_factory() as session:
                await WorkerStatusPostgresRepository(session).save(self.metrics, _utcnow())
                await session.commit()
        except Exception:
            # Visibility must never stop position management.
            logger.exception("Could not persist worker status")

    async def _sleep_until_next_cycle(self) -> None:
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=WORKER_CYCLE_SECONDS)
        except asyncio.TimeoutError:
            pass

    def stop(self) -> None:
        """Finish the current cycle, then exit the loop and release exchange clients."""
        self.is_running = False
        self._stop_requested.set()

    def _strategy_for(self, bot: Bot) -> IBotStrategy:
        if bot.strategy_type.upper() == ML_STRATEGY_NAME:
            if settings.TRADING_MODE == "live":
                # Hard rule: the model never drives real-money decisions.
                return MLSignalStrategy(None, unavailable_reason="ML strategies are disabled in live mode")
            if not settings.ML_TRADING_ENABLED:
                return MLSignalStrategy(None, unavailable_reason="ML_TRADING_ENABLED=false")
            if self.predictor is None:
                return MLSignalStrategy(None, unavailable_reason=self.predictor_error)
            if not self.predictor.approved_for_trading:
                return MLSignalStrategy(
                    None, unavailable_reason="model not approved for trading (shadow only)"
                )
            return MLSignalStrategy(self.predictor)

        strategy = StrategyFactory.get_strategy(bot.strategy_type)
        if settings.ML_SHADOW_ENABLED and self.predictor is not None:
            return ShadowRecordingStrategy(strategy, MLSignalStrategy(self.predictor))
        return strategy

    async def _record_prediction(self, bot: Bot, strategy: IBotStrategy) -> None:
        if isinstance(strategy, ShadowRecordingStrategy):
            mode, decision = "shadow", strategy.shadow_decision
            candle, used = strategy.market_candle_close, strategy.strategy_signal
            predictor = strategy.shadow.predictor
        elif isinstance(strategy, MLSignalStrategy):
            mode, decision = "active", strategy.last_decision
            candle = decision.feature_candle_close if decision else None
            used, predictor = (decision.signal if decision else None), strategy.predictor
        else:
            return
        if decision is None or predictor is None or candle is None:
            return
        key = (bot.id.value, mode)
        if self._last_logged_candle.get(key) == candle:
            return  # one record per bot, mode and closed candle
        entry = _log_entry(bot, mode, candle, decision, used, predictor)
        try:
            async with self.session_factory() as session:
                await MlPredictionLogRepository(session).record(entry)
                await session.commit()
            self._last_logged_candle[key] = candle
        except Exception:
            logger.exception("Could not record ML prediction")

    async def close_gateways(self) -> None:
        for gateway in self._gateways.values():
            await gateway.close()
        self._gateways.clear()

    async def _gateway_for(self, credential: Credential) -> IExchangeGateway:
        key = (
            "paper"
            if settings.TRADING_MODE == "paper"
            else f"{settings.TRADING_MODE}:{credential.id.value}"
        )
        gateway = self._gateways.get(key)
        if gateway is None:
            gateway = create_trading_gateway(
                trading_mode=settings.TRADING_MODE,
                live_trading_enabled=settings.LIVE_TRADING_ENABLED,
                credential=credential,
                decrypt_secret=self.encryption_service.decrypt,
                paper_taker_fee_rate=settings.PAPER_TAKER_FEE_RATE,
                paper_slippage_bps=settings.PAPER_SLIPPAGE_BPS,
                tradable_symbols=settings.tradable_symbols,
            )
            if isinstance(gateway, BybitGateway):
                # Real account (testnet or live): never trade with a key that can withdraw.
                try:
                    await gateway.verify_api_key_permissions()
                except Exception:
                    await gateway.close()
                    raise
            self._gateways[key] = gateway
        return gateway

    async def _process_bot(self, bot: Bot) -> None:
        with log_context(bot_id=str(bot.id.value)):
            await self._process_bot_in_context(bot)

    async def _process_bot_in_context(self, bot: Bot) -> None:
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

                gateway = await self._gateway_for(creds)

                trade_repo = TradePostgresRepository(session)
                strategy = self._strategy_for(bot)
                cycle = BotCycle(
                    trade_repository=trade_repo,
                    gateway=gateway,
                    strategy=strategy,
                    risk_guard=RiskGuard(trade_repo, _risk_limits()),
                    commit=session.commit,
                    rollback=session.rollback,
                )
                try:
                    outcome = await cycle.run(bot)
                finally:
                    if cycle.market_data_at is not None:
                        self.metrics.market_data_seen(cycle.market_data_at)
                    await self._record_prediction(bot, strategy)
                self.metrics.record_outcome(outcome.value)
                logger.info("Bot cycle finished: %s", outcome.value, extra={"outcome": outcome.value})
                severity = ALERTING_OUTCOMES.get(outcome)
                if severity:
                    await self.alerts.alert(
                        f"bot.{outcome.value.lower()}.{bot.id.value}", severity,
                        f"Bot {bot.name} returned {outcome.value}; manual review needed.",
                        bot_id=str(bot.id.value), outcome=outcome.value,
                    )

            except Exception as error:
                await session.rollback()
                self.metrics.record_error(error)
                self.metrics.record_outcome("ERROR")
                logger.exception("Error processing bot %s (%s)", bot.name, bot.id)
