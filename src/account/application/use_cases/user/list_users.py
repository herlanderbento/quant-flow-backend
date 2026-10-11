from dataclasses import dataclass, replace
from uuid import UUID

from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.use_cases import UseCase
from shared.domain.exceptions import UnauthorizedException
from account.application.use_cases.user.common.user_output import UserOutput
from account.domain.user_repository import IUserRepository, UserFilter, UserSearchInput, UserSearchOutput


@dataclass(slots=True)
class ListUsersInput(PaginatedListInput[UserFilter]):
    requester_id: UUID | None = None


@dataclass(slots=True)
class ListUsersOutput(PaginatedListOutput[UserOutput]):
    pass


class ListUsersUseCase(UseCase):
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    async def execute(self, input: ListUsersInput) -> ListUsersOutput:
        # There are no administrator roles: a user can only ever list themselves.
        if input.requester_id is None:
            raise UnauthorizedException("Authentication required")
        input.filter = replace(input.filter or UserFilter(), id=input.requester_id)
        search_input = UserSearchInput(**input.to_search_input())

        search_output = await self.user_repository.search(search_input)

        return self.__to_output(search_output)

    def __to_output(self, output: UserSearchOutput) -> ListUsersOutput:
        items = list(map(UserOutput.from_entity, output.items))
        return ListUsersOutput.from_search_output(items, output)