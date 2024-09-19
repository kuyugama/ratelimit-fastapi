from typing import Any, Mapping
from datetime import timedelta
import logging
import typing
import random

from fastapi import FastAPI, Depends, Request, Header
from ratelimit.ranking.redis import RedisRanking
from ratelimit.store.redis import RedisStore
from redis.asyncio import Redis

from ratelimit import (
    require_ratelimit_context,
    RatelimitContext,
    setup_ratelimit,
    BaseUser,
    LimitRule,
    ratelimit,
)

logging.basicConfig(level=logging.DEBUG)


class RateLimitUser(BaseUser):
    user_id: int | None
    address: str

    @property
    def unique_id(self):
        return self.user_id or self.address


def address(scope: Mapping[str, Any], headers: Mapping[str, Any]) -> str:
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0]
    else:
        ip = scope.get("client")[0]

    return ip


def optional_user(
    user: int | None = Header(None),
    role: typing.Literal["default", "admin"] = Header("default"),
):
    if user is None:
        return None

    return {"id": user, "role": role}


async def authority_func(
    request: Request,
    user: dict[str, int | str] | None = Depends(optional_user),
) -> RateLimitUser:
    if not user:
        return RateLimitUser(
            address=address(request.scope, request.headers), group="default"
        )

    return RateLimitUser(
        user_id=user["id"],
        address=address(request.scope, request.headers),
        group=user["role"],
    )


redis = Redis.from_url("redis://localhost:6379/1")

setup_ratelimit(
    ranking=RedisRanking(redis, RateLimitUser),
    store=RedisStore(redis),
    authentication_func=authority_func,
    user_ttl=timedelta(minutes=5).total_seconds(),
)


app = FastAPI()


@app.get(
    "/hello",
    dependencies=[
        Depends(
            ratelimit(
                (
                    LimitRule(
                        hits=10,
                        batch_time=timedelta(seconds=5).total_seconds(),
                        affected_group="default",
                        block_time=timedelta(minutes=2).total_seconds(),
                    ),
                    LimitRule(
                        delay=timedelta(seconds=1).total_seconds(),
                        increase_rank=False,
                        message="Slow down! This endpoint requires delays between requests",
                        block_time=timedelta(seconds=1).total_seconds(),
                    ),
                )
            )
        )
    ],
)
async def endpoint(
    context: RatelimitContext = Depends(require_ratelimit_context),
):
    value = random.randint(1, 128)

    if value == 18:
        context.ignore_hit()

    elif value == 19:
        context.ignore_user(for_seconds=timedelta(hours=1).total_seconds())

    elif value == 20:
        context.ignore_user(for_times=2, count_this=True)

    elif value == 21:
        context.ignore_all_users(for_seconds=timedelta(hours=1).total_seconds())

    elif value == 22:
        context.ignore_all_users(for_times=2, count_this=True)

    elif value == 27:
        context.reset_rank()

    elif value == 36:
        context.increase_rank(4)

    elif value == 48:
        context.increase_rank(-2)

    elif value == 56:
        context.limit(for_seconds=timedelta(minutes=20).total_seconds())

    elif value == 64:
        # Seconds is taken from first rule at user's rank
        context.limit(message="You're now rate-limited", reason="Fortune")

    return {
        "Ok": True,
        "value": value,
        "data": context.data,
        "rule": context.rule,
        "authority": context.authority,
    }
