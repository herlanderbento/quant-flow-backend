from abc import abstractmethod
from dataclasses import dataclass

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
    def find_open_by_bot_id(self, bot_id: BotId) -> list[Trade]:
        raise NotImplementedError()
