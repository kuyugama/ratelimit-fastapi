from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ratelimit.user import BaseUser, UserID

T = TypeVar("T", bound=BaseUser)


class BaseRanking(ABC, Generic[T]):

    def __init__(self, user_model: type[T]):
        self.user_model: type[T] = user_model

    @abstractmethod
    async def save_user(self, authority: T): ...

    @abstractmethod
    async def get_user(self, authority_id: UserID) -> T: ...
