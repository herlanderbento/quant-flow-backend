"""Create a user, a placeholder credential and paper bots for a soak test.

    TRADING_MODE=paper python -m trader.infra.ops.seed_paper_bot --symbol BTC/USDT --symbol ETH/USDT

Refuses to run unless TRADING_MODE=paper. The credential is a placeholder: paper mode
never decrypts nor uses it. The user gets a random, unusable password (not printed).
"""
import argparse
import asyncio
import secrets
import sys

from account.domain.credential import Credential
from account.domain.user import User, UserId
from account.infra.db.credential_postgres_repository import CredentialPostgresRepository
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.infra.api.dependencies import get_encryption
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from shared.infra.db.config import settings
from shared.infra.db.database import AsyncSessionLocal, engine
from trader.domain.bot import Bot, BotCreateCommand
from trader.infra.db.bot_postgres_repository import BotPostgresRepository

SOAK_EMAIL = "paper-soak@quantflow.dev"


async def seed(symbols: list[str], capital: float, stop_loss: float, take_profit: float,
               strategy: str) -> None:
    async with AsyncSessionLocal() as session:
        users = UserPostgresRepository(session)
        user = await users.find_by_email(SOAK_EMAIL)
        if user is None:
            user = User(name="Paper soak", email=SOAK_EMAIL,
                        password=BcryptHasher().hash(secrets.token_urlsafe(32)))
            await users.insert(user)

        credential = Credential(
            user_id=UserId(value=user.id.value), name="PAPER-PLACEHOLDER",
            api_key=get_encryption().encrypt("paper-placeholder"),
            api_key_hint="hold",
            api_secret=get_encryption().encrypt(secrets.token_urlsafe(16)),
            is_testnet=True, is_active=True,
        )
        await CredentialPostgresRepository(session).insert(credential)

        bots = BotPostgresRepository(session)
        for symbol in symbols:
            # Same validation as the API (implemented strategy, SL/TP bounds).
            bot = Bot.create(BotCreateCommand(
                user_id=UserId(value=user.id.value), credential_id=credential.id,
                name=f"soak-{symbol.replace('/', '-').lower()}", symbol=symbol,
                strategy_type=strategy, is_active=True, allocated_capital=capital,
                stop_loss_pct=stop_loss, take_profit_pct=take_profit,
            ))
            await bots.insert(bot)
            print(f"created bot {bot.id.value} {symbol} {strategy}")
        await session.commit()
    await engine.dispose()


def main() -> int:
    if settings.TRADING_MODE != "paper":
        print("Refusing: seed_paper_bot only runs with TRADING_MODE=paper.", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--capital", type=float, default=100.0)
    parser.add_argument("--stop-loss", type=float, default=2.0)
    parser.add_argument("--take-profit", type=float, default=4.0)
    parser.add_argument("--strategy", default="RSI_SIMPLE")
    args = parser.parse_args()
    asyncio.run(seed(args.symbol, args.capital, args.stop_loss, args.take_profit, args.strategy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
