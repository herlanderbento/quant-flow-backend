from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime

from account.domain.credential import CredentialId
from account.domain.user import UserId
from shared.domain.repository_interface import IRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput
from trader.domain.bot import BotId
from trader.domain.trade import Trade, TradeId


@dataclass
class TradeFilter:
    bot_id: BotId | None = None
    symbol: str | None = None
    status: str | None = None
    side: str | None = None


@dataclass(slots=True, kw_only=True)
class TradeSearchInput(SearchInput[TradeFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class TradeSearchOutput(SearchOutput[Trade]):
    pass


class ITradeRepository(IRepository[Trade, TradeId]):
    @abstractmethod
    def find_by_user_id(
        self, user_id: UserId, input: TradeSearchInput
    ) -> TradeSearchOutput:
        raise NotImplementedError()

    @abstractmethod
    def find_active_by_bot_id(self, bot_id: BotId) -> list[Trade]:
        """Trades in PENDING_OPEN, OPEN or PENDING_CLOSE for this bot."""
        raise NotImplementedError()

    @abstractmethod
    def find_latest_final_by_bot_id(self, bot_id: BotId) -> Trade | None:
        """Most recently finished (CLOSED or CANCELLED) trade of this bot."""
        raise NotImplementedError()

    @abstractmethod
    def realized_pnls(self, bot_id: BotId) -> list[tuple[datetime, float]]:
        """(closed_at, pnl) of the bot's closed trades, oldest first."""
        raise NotImplementedError()

    @abstractmethod
    def open_base_quantity(self, credential_id: CredentialId, base_asset: str) -> float:
        """Base quantity held by all OPEN/PENDING_CLOSE trades of bots sharing this credential."""
        raise NotImplementedError()

    @abstractmethod
    def active_exposure_by_user(self, user_id: UserId) -> float:
        """Capital committed to the user's non-final trades (cost basis, or bot capital if pending)."""
        raise NotImplementedError()
