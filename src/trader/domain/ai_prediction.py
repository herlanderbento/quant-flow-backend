from dataclasses import dataclass, field
from shared.domain.entity import AggregateRoot
from shared.domain.value_objects import Uuid
from trader.domain.bot import BotId
from shared.domain.exceptions import InvalidArgumentException

VALID_PREDICTION_SIGNALS = frozenset({"BULLISH", "BEARISH", "NEUTRAL"})


@dataclass
class AIPredictionCreateCommand:
    bot_id: BotId
    symbol: str
    ai_model_version: str
    features_payload: dict
    prediction_signal: str
    probability: float


class AIPredictionId(Uuid):
    pass


@dataclass(slots=True, kw_only=True)
class AIPrediction(AggregateRoot):
    id: AIPredictionId = field(default_factory=AIPredictionId)
    bot_id: BotId
    symbol: str
    ai_model_version: str
    features_payload: dict
    prediction_signal: str
    probability: float

    @staticmethod
    def create(command: AIPredictionCreateCommand) -> "AIPrediction":
        ai_prediction = AIPrediction(
            bot_id=command.bot_id,
            symbol=command.symbol,
            ai_model_version=command.ai_model_version,
            features_payload=command.features_payload,
            prediction_signal=command.prediction_signal,
            probability=command.probability,
        )
        ai_prediction.validate()
        return ai_prediction

    @property
    def entity_id(self) -> AIPredictionId:
        return self.id

    def validate(self) -> None:
        if self.prediction_signal not in VALID_PREDICTION_SIGNALS:
            raise InvalidArgumentException(
                "Invalid prediction signal. Must be 'BULLISH', 'BEARISH' or 'NEUTRAL'."
            )
        if not 0 <= self.probability <= 1:
            raise InvalidArgumentException(
                "Invalid probability. Must be between 0 and 1."
            )
        if not isinstance(self.features_payload, dict):
            raise InvalidArgumentException("Features payload must be a dictionary.")
        if not all(isinstance(key, str) for key in self.features_payload):
            raise InvalidArgumentException(
                "Features payload keys must be strings (feature names)."
            )
        if not all(
            isinstance(value, float) for value in self.features_payload.values()
        ):
            raise InvalidArgumentException("Features payload values must be floats.")
