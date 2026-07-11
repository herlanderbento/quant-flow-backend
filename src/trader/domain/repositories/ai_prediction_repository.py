from abc import abstractmethod
from dataclasses import dataclass

from shared.domain.repository_interface import ISearchableRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput
from trader.domain.ai_prediction import AIPrediction, AIPredictionId
from trader.domain.bot import BotId


@dataclass
class AIPredictionFilter:
    bot_id: BotId | None = None
    symbol: str | None = None
    ai_model_version: str | None = None
    prediction_signal: str | None = None
    probability: float | None = None


@dataclass(slots=True, kw_only=True)
class AIPredictionSearchInput(SearchInput[AIPredictionFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class AIPredictionSearchOutput(SearchOutput[AIPrediction]):
    pass


class IAIPredictionRepository(ISearchableRepository[AIPrediction, AIPredictionId]):
    @abstractmethod
    def find_by_bot_id(
        self, bot_id: BotId, input: AIPredictionSearchInput
    ) -> AIPredictionSearchOutput:
        raise NotImplementedError()
