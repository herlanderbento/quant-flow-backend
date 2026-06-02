from abc import abstractmethod
from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.exchange_credential import ExchangeCredential, ExchangeCredentialId
from shared.domain.repository_interface import ISearchableRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput


@dataclass
class ExchangeCredentialFilter:
    user_id: UserId | None = None
    exchange_name: str | None = None
    is_testnet: bool | None = None


@dataclass(slots=True, kw_only=True)
class ExchangeCredentialSearchInput(SearchInput[ExchangeCredentialFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class ExchangeCredentialSearchOutput(SearchOutput[ExchangeCredential]):
    pass


class IExchangeCredentialRepository(
    ISearchableRepository[ExchangeCredential, ExchangeCredentialId]
):
    @abstractmethod
    def find_by_user_id(
        self, user_id: UserId, input: ExchangeCredentialSearchInput
    ) -> ExchangeCredentialSearchOutput:
        raise NotImplementedError()

    @abstractmethod
    def find_by_user_exchange(
        self, user_id: UserId, exchange_name: str, is_testnet: bool
    ) -> ExchangeCredential | None:
        raise NotImplementedError()
