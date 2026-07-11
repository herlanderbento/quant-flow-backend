from trader.domain.interface.strategy_interface import IBotStrategy, MarketData, TradeSignal

class SimpleRsiStrategy(IBotStrategy):
    def __init__(self, rsi_period: int = 14, overbought: float = 70.0, oversold: float = 30.0):
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold

    @property
    def name(self) -> str:
        return "RSI_SIMPLE"

    async def analyze(self, market_data: MarketData) -> TradeSignal:
        # Extract the RSI value (assumed to be calculated by the Worker or the AI)
        current_rsi = market_data.indicators.get("rsi")
        
        # Protection: if we don't have enough data, we don't trade
        if current_rsi is None:
            return TradeSignal.HOLD
            
        # Trading logic
        if current_rsi <= self.oversold:
            return TradeSignal.BUY
            
        elif current_rsi >= self.overbought:
            return TradeSignal.SELL
            
        return TradeSignal.HOLD