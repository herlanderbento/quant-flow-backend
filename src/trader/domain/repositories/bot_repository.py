from abc import abstractmethod
from dataclasses import dataclass

from account.domain.user import UserId
from shared.domain.repository_interface import ISearchableRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput
from trader.domain.bot import Bot, BotId


@dataclass
class BotFilter:
    name: str | None = None
    strategy_type: str | None = None
    is_active: bool | None = None


@dataclass(slots=True, kw_only=True)
class BotSearchInput(SearchInput[BotFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class BotSearchOutput(SearchOutput[Bot]):
    pass


class IBotRepository(ISearchableRepository[Bot, BotId]):
    @abstractmethod
    def find_by_user_id(
        self, user_id: UserId, input: BotSearchInput
    ) -> BotSearchOutput:
        raise NotImplementedError()

    @abstractmethod
    def find_active(self) -> list[Bot]:
        raise NotImplementedError()

    @abstractmethod
    def find_active_by_user(self, user_id: UserId) -> list[Bot]:
        raise NotImplementedError()

    @abstractmethod
    def find_needing_processing(self) -> list[Bot]:
        """Active bots plus inactive bots that still hold a non-final trade."""
        raise NotImplementedError()
