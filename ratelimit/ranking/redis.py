from typing import Callable, TypeVar, Generic

from redis.asyncio import Redis

from ratelimit.ranking.base import BaseRanking
from ratelimit.user import UserID
from ratelimit import BaseUser, config


def key_maker(user_id: UserID) -> str:
    return f"authority:{user_id}"


T = TypeVar("T", bound=BaseUser)


class RedisRanking(BaseRanking, Generic[T]):
    def __init__(
        self,
        redis: Redis,
        authority_model: type[T],
        key_maker: Callable[[UserID], str] = key_maker,
    ):
        super().__init__(authority_model)
        self._redis = redis
        self.key_maker = key_maker

    async def save_user(self, user: T) -> None:
        await self._redis.set(
            self.key_maker(user),
            user.model_dump_json(),
            ex=config.USER_TTL,
        )

    async def get_user(self, user_id: UserID) -> T | None:
        data = await self._redis.get(self.key_maker(user_id))

        if not data:
            return None

        return self.authority_model.model_validate_json(data)
