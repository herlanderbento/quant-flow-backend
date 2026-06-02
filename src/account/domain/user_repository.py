from abc import abstractmethod
from dataclasses import dataclass, field

from account.domain.user import User, UserId
from shared.domain.repository_interface import ISearchableRepository
from shared.domain.search_input import SearchInput
from shared.domain.search_output import SearchOutput


@dataclass(frozen=True, slots=True)
class UserFilter:
    name: str | None = field(default=None)
    email: str | None = field(default=None)
    is_active: bool | None = field(default=None)

@dataclass(slots=True, kw_only=True)
class UserSearchInput(SearchInput[UserFilter]):
    pass


@dataclass(slots=True, kw_only=True)
class UserSearchOutput(SearchOutput[User]):
    pass

class IUserRepository(ISearchableRepository[User, UserId]):
    @abstractmethod
    def find_by_email(self, email: str) -> User | None:
        raise NotImplementedError()
