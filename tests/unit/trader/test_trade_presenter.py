from trader.application.use_cases.trade.common.trade_output import TradeOutput
from trader.domain.bot import BotId
from trader.domain.trade import Trade, TradePendingCommand
from trader.infra.api.trade.trade_presenter import TradePresenter


def test_pending_trade_without_price_is_presentable():
    trade = Trade.open_pending(
        TradePendingCommand(
            bot_id=BotId(), symbol="BTC/USDT", side="BUY",
            requested_quantity=0.002, client_order_id="qf-1",
        )
    )
    presented = TradePresenter.from_output(TradeOutput.from_entity(trade))
    assert presented.status == "PENDING_OPEN"
    assert presented.price_executed is None
