"""Persist domain objects through the real repositories (same code paths as the app)."""
import uuid

from account.domain.credential import Credential
from account.domain.user import User, UserId
from account.infra.db.credential_postgres_repository import CredentialPostgresRepository
from account.infra.db.user_postgres_repository import UserPostgresRepository
from shared.infra.cryptography.bcrypt_hasher import BcryptHasher
from trader.domain.bot import Bot
from trader.infra.db.bot_postgres_repository import BotPostgresRepository

TEST_PASSWORD = "integration-only-password"


async def create_user(session_factory, *, active=True, password=TEST_PASSWORD) -> User:
    user = User(
        name="Integration",
        email=f"{uuid.uuid4().hex}@quantflow.dev",
        password=BcryptHasher().hash(password),
        is_active=active,
    )
    async with session_factory() as session:
        await UserPostgresRepository(session).insert(user)
    return user


async def create_credential(session_factory, user: User, *, is_testnet=True) -> Credential:
    credential = Credential(
        user_id=UserId(value=user.id.value),
        name="BYBIT",
        api_key="integration-key",
        api_secret="not-a-real-secret",
        is_testnet=is_testnet,
        is_active=True,
    )
    async with session_factory() as session:
        await CredentialPostgresRepository(session).insert(credential)
    return credential


async def create_bot(session_factory, user: User, credential: Credential, **overrides) -> Bot:
    data = dict(
        user_id=UserId(value=user.id.value),
        credential_id=credential.id,
        name="integration-bot",
        symbol="BTC/USDT",
        strategy_type="RSI_SIMPLE",
        is_active=True,
        allocated_capital=100.0,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
    )
    data.update(overrides)
    bot = Bot(**data)
    async with session_factory() as session:
        await BotPostgresRepository(session).insert(bot)
        await session.commit()
    return bot


async def create_bot_setup(session_factory, **bot_overrides):
    user = await create_user(session_factory)
    credential = await create_credential(session_factory, user)
    bot = await create_bot(session_factory, user, credential, **bot_overrides)
    return user, credential, bot
