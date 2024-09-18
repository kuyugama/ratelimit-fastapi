from typing import Callable

from redis.asyncio import Redis
import pydantic

from ratelimit.user import UserID
from ratelimit.endpoint import Endpoint
from ratelimit import BaseUser
from ratelimit import config
from .base import BaseStore


def key_maker(endpoint: Endpoint, authority: UserID | None = None) -> str:
    key = f"endpoint:{endpoint.method}:{endpoint.path}"
    if authority:
        key += f":authority:{authority}"

    return key


class RedisStore(BaseStore):
    def __init__(
        self,
        redis: Redis,
        key_maker: (
            Callable[[Endpoint], str] | Callable[[Endpoint, UserID], str]
        ) = key_maker,
    ):
        self._redis = redis
        self.key_maker = key_maker

    async def get_endpoint(self, path: str, method: str) -> Endpoint:
        default = Endpoint(path=path, method=method)
        data = await self._redis.get(self.key_maker(default))

        if not data:
            return default

        return Endpoint.model_validate_json(data)

    async def save_endpoint(self, endpoint: Endpoint) -> None:
        await self._redis.set(
            self.key_maker(endpoint),
            endpoint.model_dump_json(),
            ex=config.ENDPOINT_TTL,
        )

    async def get_user_endpoint(
        self, path: str, method: str, user_id: UserID
    ) -> Endpoint:
        default = Endpoint(path=path, method=method)

        data = await self._redis.get(self.key_maker(default, user_id))

        if not data:
            return Endpoint(
                path=path,
                method=method,
            )

        return Endpoint.model_validate_json(data)

    async def save_user_endpoint(
        self, endpoint: Endpoint, user: BaseUser
    ) -> None:
        await self._redis.set(
            self.key_maker(endpoint, user.unique_id),
            endpoint.model_dump_json(),
            ex=config.USER_ENDPOINT_TTL,
        )
