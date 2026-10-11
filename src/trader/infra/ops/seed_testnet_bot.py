"""Bybit Testnet setup: read-only account checks first, then the encrypted credential and bots.

    # read-only: endpoint, key permissions, account type, balances, instrument limits
    python -m trader.infra.ops.seed_testnet_bot --check --symbol BTC/USDT --symbol ETH/USDT
    # same checks, then store the credential (encrypted) and create the bots (inactive)
    python -m trader.infra.ops.seed_testnet_bot --symbol BTC/USDT --symbol ETH/USDT --capital 20

Keys are read from BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET and are never printed,
logged or stored unencrypted. Refuses unless TRADING_MODE=testnet and
LIVE_TRADING_ENABLED=false, and refuses any endpoint other than the Bybit testnet.
Bots are created inactive unless --activate is given.
"""
import argparse
import asyncio
import os
import secrets
import sys
from typing import Callable

from account.domain.credential import Credential, CredentialCreateCommand
from account.domain.user import User, UserId
from account.infra.db.credential_postgres_repository import CredentialPostgresRepository
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.infra.api.dependencies import get_encryption
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from shared.infra.db.config import settings
from shared.infra.db.database import AsyncSessionLocal, engine
from trader.domain.bot import Bot, BotCreateCommand
from trader.infra.db.bot_postgres_repository import BotPostgresRepository
from trader.infra.gateway.bybit_gateway import TESTNET_HOST, BybitGateway

TESTNET_EMAIL = "testnet-ops@quantflow.dev"
CREDENTIAL_NAME = "BYBIT-TESTNET"
KEY_ENV = "BYBIT_TESTNET_API_KEY"
SECRET_ENV = "BYBIT_TESTNET_API_SECRET"
MAX_CLOCK_SKEW_MS = 3000


class Refused(Exception):
    pass


def refuse_unless_testnet_mode() -> None:
    if settings.TRADING_MODE != "testnet":
        raise Refused("seed_testnet_bot only runs with TRADING_MODE=testnet.")
    if settings.LIVE_TRADING_ENABLED:
        raise Refused("LIVE_TRADING_ENABLED must be false in a testnet environment.")


def read_keys() -> tuple[str, str]:
    key, secret = os.environ.get(KEY_ENV, ""), os.environ.get(SECRET_ENV, "")
    if not key or not secret:
        raise Refused(f"{KEY_ENV} and {SECRET_ENV} must be set (testnet keys only).")
    return key, secret


async def check_account(gateway: BybitGateway, symbols: list[str], capital: float | None) -> None:
    """Read-only. Raises on anything unsafe; prints a summary without secrets.

    `capital=None` skips the per-bot allocation checks.
    """
    hosts = gateway.api_hosts()
    if hosts != {TESTNET_HOST}:
        raise Refused(f"Endpoint is not the Bybit testnet: {sorted(hosts)}")
    print(f"endpoint: {TESTNET_HOST}")

    # Signed requests are refused outside Bybit's recv_window (5 s by default).
    server_ms = await gateway.exchange.fetch_time()
    skew_ms = server_ms - gateway.clock_ms()
    print(f"clock skew vs exchange: {skew_ms} ms")
    if abs(skew_ms) > MAX_CLOCK_SKEW_MS:
        raise Refused(f"local clock differs from the exchange by {skew_ms} ms; sync the clock")

    granted = await gateway.verify_api_key_permissions()  # allow-list policy, UTA, read-write
    print(f"api key: read-write, unified trading account, permissions {granted} "
          "(all within the allow-list; orders limited to spot markets)")

    quote_needed = 0.0
    for symbol in symbols:
        base, quote = symbol.split("/", 1)
        rules = await gateway.get_trading_rules(symbol)
        price = await gateway.get_current_price(symbol)
        missing = [name for name in ("amount_step", "min_amount", "min_cost")
                   if getattr(rules, name) is None]
        if missing:
            raise Refused(f"{symbol}: instrument filters missing from the exchange response: {missing}")
        minimum = max(rules.min_cost or 0.0, (rules.min_amount or 0.0) * price)
        print(f"{symbol}: price {price} step {rules.amount_step} min_qty {rules.min_amount} "
              f"min_value {rules.min_cost} max_qty {rules.max_amount} max_value {rules.max_cost} "
              f"-> smallest order ≈ {minimum:.2f} {quote}")
        if capital is not None and capital < minimum:
            raise Refused(f"--capital {capital} is below the {symbol} minimum order ({minimum:.2f}).")
        print(f"balance {base}: {await gateway.get_balance(base)}")
        quote_needed += capital or 0.0
    quote = symbols[0].split("/", 1)[1]
    available = await gateway.get_balance(quote)
    print(f"balance {quote}: {available}" + (f" (bots would allocate {quote_needed})" if capital else ""))
    if capital is not None and available is not None and available < quote_needed:
        print(f"warning: {quote} balance below the total allocation; entries will be refused "
              "with INSUFFICIENT_BALANCE until the testnet account is funded.")


async def store(api_key: str, api_secret: str, symbols: list[str], capital: float,
                stop_loss: float, take_profit: float, strategy: str, activate: bool) -> None:
    encryption = get_encryption()
    async with AsyncSessionLocal() as session:
        users = UserPostgresRepository(session)
        user = await users.find_by_email(TESTNET_EMAIL)
        if user is None:
            user = User(name="Testnet operations", email=TESTNET_EMAIL,
                        password=BcryptHasher().hash(secrets.token_urlsafe(32)))
            await users.insert(user)
        user_id = UserId(value=user.id.value)

        credentials = CredentialPostgresRepository(session)
        for previous in await credentials.find_active_by_user(user_id.value, CREDENTIAL_NAME, True):
            previous.deactivate()
            await credentials.update(previous)
        credential = Credential.create(CredentialCreateCommand(
            user_id=user_id, name=CREDENTIAL_NAME,
            api_key=encryption.encrypt(api_key), api_secret=encryption.encrypt(api_secret),
            is_testnet=True, api_key_hint=api_key[-4:],
        ))
        await credentials.insert(credential)
        print(f"stored credential {credential.id.value} (testnet, encrypted, key …{api_key[-4:]})")

        bots = BotPostgresRepository(session)
        for symbol in symbols:
            bot = Bot.create(BotCreateCommand(
                user_id=user_id, credential_id=credential.id,
                name=f"testnet-{symbol.replace('/', '-').lower()}", symbol=symbol,
                strategy_type=strategy, is_active=activate, allocated_capital=capital,
                stop_loss_pct=stop_loss, take_profit_pct=take_profit,
            ))
            await bots.insert(bot)
            print(f"created bot {bot.id.value} {symbol} {strategy} active={activate}")
        await session.commit()


async def run(args, gateway_factory: Callable[[str, str], BybitGateway] | None = None) -> None:
    refuse_unless_testnet_mode()
    api_key, api_secret = read_keys()
    factory = gateway_factory or (lambda k, s: BybitGateway(
        k, s, is_testnet=True, tradable_symbols=settings.tradable_symbols))
    gateway = factory(api_key, api_secret)
    try:
        await check_account(gateway, args.symbol, args.capital)
    finally:
        await gateway.close()
    if args.check:
        print("check only: nothing written")
        return
    try:
        await store(api_key, api_secret, args.symbol, args.capital, args.stop_loss,
                    args.take_profit, args.strategy, args.activate)
    finally:
        await engine.dispose()


def parse(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--check", action="store_true", help="read-only checks; write nothing")
    parser.add_argument("--capital", type=float, default=20.0)
    parser.add_argument("--stop-loss", type=float, default=2.0)
    parser.add_argument("--take-profit", type=float, default=4.0)
    parser.add_argument("--strategy", default="RSI_SIMPLE")
    parser.add_argument("--activate", action="store_true", help="create the bots already active")
    return parser.parse_args(argv)


def main() -> int:
    args = parse()
    try:
        asyncio.run(run(args))
    except Refused as e:
        print(f"Refusing: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - message only; never the keys
        print(f"Testnet check failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
