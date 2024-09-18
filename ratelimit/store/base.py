from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ratelimit.user import UserID, BaseUser


if TYPE_CHECKING:
    from ratelimit.endpoint import Endpoint


class BaseStore(ABC):
    @abstractmethod
    async def save_endpoint(self, endpoint: "Endpoint") -> None: ...

    @abstractmethod
    async def get_endpoint(self, path: str, method: str) -> "Endpoint": ...

    @abstractmethod
    async def save_user_endpoint(
        self, endpoint: "Endpoint", user: BaseUser
    ) -> None: ...

    @abstractmethod
    async def get_user_endpoint(
        self, path: str, method: str, user_id: UserID
    ) -> "Endpoint": ...
