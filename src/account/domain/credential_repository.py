from abc import abstractmethod
from dataclasses import dataclass

from account.domain.user import UserId
from account.domain.credential import Credential, CredentialId
from shared.domain.repository_interface import ISearchableRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput


@dataclass
class CredentialFilter:
    name: str | None = None
    is_testnet: bool | None = None
    is_active: bool | None = None


@dataclass(slots=True, kw_only=True)
class CredentialSearchInput(SearchInput[CredentialFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class CredentialSearchOutput(SearchOutput[Credential]):
    pass


class ICredentialRepository(
    ISearchableRepository[Credential, CredentialId]
):
    @abstractmethod
    def find_by_user_id(
        self, user_id: UserId, input: CredentialSearchInput
    ) -> CredentialSearchOutput:
        raise NotImplementedError()

    @abstractmethod
    def find_active_by_user(
            self, user_id: UserId, name: str, is_testnet: bool
    ) -> list[Credential]:
        raise NotImplementedError()
