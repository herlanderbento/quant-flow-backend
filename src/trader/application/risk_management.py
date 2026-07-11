from dataclasses import dataclass


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None = None


def evaluate_exit(
    *,
    side: str,
    entry_price: float,
    current_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> ExitDecision:
    if entry_price <= 0 or current_price <= 0:
        return ExitDecision(should_exit=False)

    if side == "BUY":
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    elif side == "SELL":
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    else:
        return ExitDecision(should_exit=False)

    if pnl_pct <= -stop_loss_pct:
        return ExitDecision(should_exit=True, reason="STOP_LOSS")
    if pnl_pct >= take_profit_pct:
        return ExitDecision(should_exit=True, reason="TAKE_PROFIT")

    return ExitDecision(should_exit=False)
