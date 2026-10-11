from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.domain.exceptions import EntityValidationException
from trader.application.risk_guard import RiskGuard, RiskLimits
from trader.domain.bot import Bot, BotCreateCommand

NOW = datetime(2026, 10, 10, 15, tzinfo=timezone.utc)
YESTERDAY = NOW - timedelta(days=1)


def _bot(capital=100.0):
    return Bot(user_id=UserId(), credential_id=CredentialId(), name="b", symbol="BTC/USDT",
               strategy_type="RSI_SIMPLE", is_active=True, allocated_capital=capital,
               stop_loss_pct=2.0, take_profit_pct=4.0)


def _guard(history=(), exposure=0.0, **limits):
    repo = AsyncMock()
    repo.realized_pnls.return_value = list(history)
    repo.active_exposure_by_user.return_value = exposure
    return RiskGuard(repo, RiskLimits(**limits), clock=lambda: NOW)


async def test_allows_entry_within_limits():
    verdict = await _guard(history=[(YESTERDAY, -1.0), (NOW, -1.0)]).check_entry(_bot())
    assert verdict.allowed


async def test_global_halt_blocks():
    verdict = await _guard(trading_halted=True).check_entry(_bot())
    assert (verdict.allowed, verdict.reason) == (False, "TRADING_HALTED")


async def test_daily_loss_limit_counts_only_today():
    guard = _guard(history=[(YESTERDAY, -10.0), (NOW, -3.0)], max_daily_loss_pct=3.0)
    verdict = await guard.check_entry(_bot(100.0))
    assert verdict.reason == "MAX_DAILY_LOSS"

    guard = _guard(history=[(YESTERDAY, -10.0), (NOW, -2.9)], max_daily_loss_pct=3.0,
                   max_drawdown_pct=50)
    assert (await guard.check_entry(_bot(100.0))).allowed


async def test_drawdown_is_measured_from_the_realized_peak():
    # +15 then -11 => 11% below peak although total PnL is positive
    guard = _guard(history=[(YESTERDAY - timedelta(days=3), 15.0),
                            (YESTERDAY - timedelta(days=2), -6.0),
                            (YESTERDAY, -5.0)], max_drawdown_pct=10.0)
    verdict = await guard.check_entry(_bot(100.0))
    assert verdict.reason == "MAX_DRAWDOWN"


async def test_user_exposure_includes_the_new_entry():
    guard = _guard(exposure=950.0, max_user_exposure=1000.0)
    assert (await guard.check_entry(_bot(100.0))).reason == "MAX_USER_EXPOSURE"
    guard = _guard(exposure=900.0, max_user_exposure=1000.0)
    assert (await guard.check_entry(_bot(100.0))).allowed


@pytest.mark.parametrize("stop_loss, take_profit", [(0.0, 4.0), (100.0, 4.0), (2.0, 0.0)])
def test_bot_rejects_zero_or_total_stops_and_zero_targets(stop_loss, take_profit):
    with pytest.raises(EntityValidationException):
        Bot.create(BotCreateCommand(
            user_id=UserId(), credential_id=CredentialId(), name="b", symbol="BTC/USDT",
            strategy_type="RSI_SIMPLE", is_active=False, allocated_capital=100.0,
            stop_loss_pct=stop_loss, take_profit_pct=take_profit))


async def test_halt_use_case_deactivates_all_active_bots():
    from trader.application.use_cases.bot.halt_user_bots import (
        HaltUserBotsInput,
        HaltUserBotsUseCase,
    )
    bots = [_bot(), _bot()]
    repo = AsyncMock()
    repo.find_active_by_user.return_value = bots
    output = await HaltUserBotsUseCase(repo).execute(HaltUserBotsInput(user_id=UserId()))
    assert all(not b.is_active for b in bots)
    assert repo.update.await_count == 2
    assert len(output.deactivated_bot_ids) == 2


@pytest.mark.parametrize("strategy", ["LSTM_AI_PREDICTOR", "SCALPER_LSTM", "UNKNOWN"])
def test_bot_rejects_unimplemented_strategies(strategy):
    with pytest.raises(EntityValidationException):
        Bot.create(BotCreateCommand(
            user_id=UserId(), credential_id=CredentialId(), name="b", symbol="BTC/USDT",
            strategy_type=strategy, is_active=False, allocated_capital=100.0,
            stop_loss_pct=2.0, take_profit_pct=4.0))
