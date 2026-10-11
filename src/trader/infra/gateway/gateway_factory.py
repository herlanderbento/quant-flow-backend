from typing import Callable

from account.domain.credential import Credential
from shared.domain.exceptions import TradingModeException
from trader.domain.interface.exchange_gateway_interface import IExchangeGateway
from trader.infra.gateway.bybit_gateway import (
    DEFAULT_TRADABLE_SYMBOLS,
    MAINNET_HOST,
    TESTNET_HOST,
    BybitGateway,
)
from trader.infra.gateway.paper_gateway import PaperExchangeGateway

TRADING_MODE_PAPER = "paper"
TRADING_MODE_TESTNET = "testnet"
TRADING_MODE_LIVE = "live"


def create_trading_gateway(
    *,
    trading_mode: str,
    live_trading_enabled: bool,
    credential: Credential,
    decrypt_secret: Callable[[str], str],  # decrypts both the stored key and secret
    paper_taker_fee_rate: float,
    paper_slippage_bps: float,
    tradable_symbols: frozenset[str] = DEFAULT_TRADABLE_SYMBOLS,
) -> IExchangeGateway:
    """Single entry point for any gateway that can place orders."""
    if trading_mode == TRADING_MODE_PAPER:
        # The credential is intentionally not decrypted nor used.
        return PaperExchangeGateway.with_public_market_data(
            paper_taker_fee_rate, paper_slippage_bps, tradable_symbols
        )

    if trading_mode == TRADING_MODE_TESTNET:
        if not credential.is_testnet:
            raise TradingModeException(
                "TRADING_MODE=testnet refuses a mainnet credential."
            )
        return _on_host(BybitGateway(
            decrypt_secret(credential.api_key), decrypt_secret(credential.api_secret),
            is_testnet=True, tradable_symbols=tradable_symbols,
        ), TESTNET_HOST)

    if trading_mode == TRADING_MODE_LIVE:
        if not live_trading_enabled:
            raise TradingModeException(
                "TRADING_MODE=live requires LIVE_TRADING_ENABLED=true."
            )
        if credential.is_testnet:
            raise TradingModeException(
                "TRADING_MODE=live refuses a testnet credential."
            )
        return _on_host(BybitGateway(
            decrypt_secret(credential.api_key), decrypt_secret(credential.api_secret),
            is_testnet=False, tradable_symbols=tradable_symbols,
        ), MAINNET_HOST)

    raise TradingModeException(f"Unknown TRADING_MODE '{trading_mode}'.")


def _on_host(gateway: BybitGateway, host: str) -> BybitGateway:
    """Second, independent check of the resolved endpoint before the gateway is used."""
    if gateway.api_hosts() != {host}:
        raise TradingModeException(
            f"Refusing gateway: expected only {host}, resolved {sorted(gateway.api_hosts())}."
        )
    return gateway
