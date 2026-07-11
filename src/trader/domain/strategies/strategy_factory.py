from trader.domain.interface.strategy_interface import IBotStrategy
from trader.domain.strategies.simple_rsi_strategy import SimpleRsiStrategy
from shared.domain.exceptions import InvalidArgumentException

_STRATEGY_IMPL: dict[str, IBotStrategy] = {
    "RSI_SIMPLE": SimpleRsiStrategy(rsi_period=14, overbought=70, oversold=30),
}

STRATEGY_ALIASES: dict[str, str] = {
    "RSI_SIMPLE": "RSI_SIMPLE",
    "SMA_RSI": "RSI_SIMPLE",
}


class StrategyFactory:
    @staticmethod
    def get_strategy(strategy_name: str) -> IBotStrategy:
        canonical = STRATEGY_ALIASES.get(strategy_name.upper())
        if not canonical:
            raise InvalidArgumentException(
                f"The strategy '{strategy_name}' is not registered in the system."
            )
        strategy = _STRATEGY_IMPL.get(canonical)
        if not strategy:
            raise InvalidArgumentException(
                f"The strategy '{strategy_name}' is accepted but not yet implemented."
            )
        return strategy
