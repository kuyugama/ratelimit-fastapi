from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ratelimit.user import BaseUser, UserID

T = TypeVar("T", bound=BaseUser)


class BaseRanking(ABC, Generic[T]):

    def __init__(self, authority_model: type[T]):
        self.authority_model: type[T] = authority_model

    @abstractmethod
    async def save_user(self, authority: T): ...

    @abstractmethod
    async def get_user(self, authority_id: UserID) -> T: ...
