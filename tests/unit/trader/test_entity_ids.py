from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.domain.exceptions import InvalidUuidException
from trader.domain.ai_prediction import AIPredictionId
from trader.domain.bot import BotId
from trader.domain.trade import Trade, TradeId, TradePendingCommand
from trader.infra.db import bot_postgres_repository, trade_postgres_repository
from trader.infra.db.sql_models import BotConfigModel


class TestUuidValueObject:
    def test_accepts_string_and_normalizes_to_uuid(self):
        raw = uuid4()
        bot_id = BotId(str(raw))
        assert isinstance(bot_id.value, UUID)
        assert bot_id == BotId(value=raw)

    def test_rejects_invalid_string(self):
        with pytest.raises(ValueError):
            BotId("not-a-uuid")

    def test_rejects_non_uuid_value(self):
        with pytest.raises(InvalidUuidException):
            BotId(value=123)

    def test_trade_and_prediction_ids_have_defaults(self):
        assert isinstance(TradeId().value, UUID)
        assert isinstance(AIPredictionId().value, UUID)

def _command(**overrides) -> TradePendingCommand:
    data = dict(
        bot_id=BotId(),
        symbol="BTC/USDT",
        side="BUY",
        requested_quantity=0.002,
        client_order_id="qf-test-1",
    )
    data.update(overrides)
    return TradePendingCommand(**data)


class TestTradePersistenceMapping:
    def test_trade_open_pending_works(self):
        trade = Trade.open_pending(_command())
        assert isinstance(trade.id, TradeId)
        assert trade.status == "PENDING_OPEN"
        assert trade.price_executed is None

    def test_trade_roundtrip_through_orm_model(self):
        prediction_id = AIPredictionId()
        trade = Trade.open_pending(_command(ai_prediction_id=prediction_id))
        trade.confirm_entry(
            exchange_order_id="ex-1",
            average_price=50000.0,
            net_quantity=0.001998,
            gross_cost=100.0,
            fee_in_quote=0.1,
        )

        model = trade_postgres_repository._to_model(trade)
        assert model.id == trade.id.value
        assert model.ai_prediction_id == prediction_id.value
        assert model.client_order_id == "qf-test-1"

        # Simulate what asyncpg returns: UUID objects and Decimal numerics
        model.price_executed = Decimal("50000.00000000")
        model.quantity = Decimal("0.00199800")
        model.open_quantity = Decimal("0.00199800")
        model.entry_cost = Decimal("100.00000000")
        model.fee_paid = Decimal("0.10000000")
        restored = trade_postgres_repository._to_entity(model)

        assert restored.id == trade.id
        assert restored.bot_id == trade.bot_id
        assert restored.ai_prediction_id == prediction_id
        assert restored.status == "OPEN"
        for value in (restored.price_executed, restored.quantity,
                      restored.open_quantity, restored.entry_cost, restored.fee_paid):
            assert type(value) is float

    def test_spot_entries_must_be_buy(self):
        with pytest.raises(Exception):
            Trade.open_pending(_command(side="SELL"))



class TestBotPersistenceMapping:
    def test_bot_loads_from_orm_model(self):
        model = BotConfigModel(
            id=uuid4(),
            user_id=uuid4(),
            credential_id=uuid4(),
            name="bot",
            symbol="BTC/USDT",
            strategy_type="RSI_SIMPLE",
            is_active=True,
            allocated_capital=Decimal("100.00000000"),
            stop_loss_pct=Decimal("2.00"),
            take_profit_pct=Decimal("4.00"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        bot = bot_postgres_repository._to_entity(model)
        assert bot.id.value == model.id
        assert isinstance(bot.user_id, UserId)
        assert isinstance(bot.credential_id, CredentialId)

    def test_bot_numeric_columns_become_float(self):
        model = BotConfigModel(
            id=uuid4(),
            user_id=uuid4(),
            credential_id=uuid4(),
            name="bot",
            symbol="BTC/USDT",
            strategy_type="RSI_SIMPLE",
            is_active=True,
            allocated_capital=Decimal("100.00000000"),
            stop_loss_pct=Decimal("2.00"),
            take_profit_pct=Decimal("4.00"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        bot = bot_postgres_repository._to_entity(model)
        for value in (bot.allocated_capital, bot.stop_loss_pct, bot.take_profit_pct):
            assert type(value) is float
