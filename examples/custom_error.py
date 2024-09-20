from datetime import timedelta, datetime
import random

from fastapi import FastAPI, Depends, Request, status
from ratelimit.ranking.redis import RedisRanking
from ratelimit.store.redis import RedisStore
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from pydantic import BaseModel

from ratelimit import (
    RateLimitedError,
    setup_ratelimit,
    ratelimit,
    LimitRule,
    BaseUser,
)

redis = Redis.from_url("redis://localhost:6379/1")


class User(BaseUser):
    address: str

    @property
    def unique_id(self):
        return self.address


def auth_func(request: Request):
    return User(address=request.client.host, group="user")


app = FastAPI()

setup_ratelimit(
    app,
    ranking=RedisRanking(redis, User),
    store=RedisStore(redis),
    authentication_func=auth_func,
)


class ErrorResponseSchema(BaseModel):
    message: str | None
    reason: str
    limited_for: int
    limited_at: datetime


@app.exception_handler(RateLimitedError)
async def on_ratelimit_error(_, exc: RateLimitedError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "message": exc.message,
            "reason": exc.reason,
            "limited_for": exc.limited_for,
            "limited_at": exc.limited_at.isoformat(),
        },
    )


@app.get(
    "/",
    dependencies=[
        Depends(
            ratelimit(
                LimitRule(
                    hits=120,
                    batch_time=timedelta(minutes=1).total_seconds(),
                )
            )
        )
    ],
    responses={429: {"model": ErrorResponseSchema}},
)
def home(a: int = 10, b: int = 30):
    if a > b:
        a, b = b, a

    if a == b:
        a, b = 10, 30

    return {"random_value": random.randint(a, b)}
