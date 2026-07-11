from abc import abstractmethod
from dataclasses import dataclass

from account.domain.user import UserId
from shared.domain.repository_interface import IRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput
from trader.domain.backtest_result import BacktestResult, BacktestResultId
from trader.domain.bot import BotId


@dataclass
class BacktestFilter:
    bot_id: BotId | None = None
    symbol: str | None = None
    strategy_type: str | None = None

@dataclass(slots=True, kw_only=True)
class BacktestSearchInput(SearchInput[BacktestFilter]):
    pass

@dataclass(slots=True, kw_only=True)
class BacktestSearchOutput(SearchOutput[BacktestResult]):
    pass

class IBacktestRepository(IRepository[BacktestResult, BacktestResultId]):
    @abstractmethod
    def find_by_user_id(
        self, user_id: UserId, input: BacktestSearchInput
    ) -> BacktestSearchOutput:
        raise NotImplementedError()
