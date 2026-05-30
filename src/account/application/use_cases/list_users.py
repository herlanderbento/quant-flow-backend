from dataclasses import dataclass

from shared.application.paginated_list_output import PaginatedListOutput
from shared.application.paginated_list_input import PaginatedListInput
from shared.application.use_cases import UseCase
from account.application.use_cases.common.user_output import UserOutput
from account.domain.user_repository import IUserRepository, UserFilter, UserSearchInput, UserSearchOutput


@dataclass(slots=True)
class ListUsersInput(PaginatedListInput[UserFilter]):
    pass


@dataclass(slots=True)
class ListUsersOutput(PaginatedListOutput[UserOutput]):
    pass


class ListUsersUseCase(UseCase):
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    def execute(self, input: ListUsersInput) -> ListUsersOutput:
        search_input = UserSearchInput(**input.to_input())

        search_output = self.user_repository.search(search_input)

        return self.__to_output(search_output)

    def __to_output(self, output: UserSearchOutput) -> ListUsersOutput:
        items = list(map(UserOutput.from_entity, output.items))
        return ListUsersOutput.from_search_output(items, output)