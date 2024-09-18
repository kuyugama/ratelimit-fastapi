from datetime import datetime, timedelta
import typing
import math

from fastapi import HTTPException, status
from typing_extensions import TypedDict

from .rule import LimitRule
from .util import utcnow


class ErrorDict(TypedDict):
    reason: str
    message: str | None
    limited_for: int
    error_type: typing.Literal[
        "ratelimit.delay_exceeded", "ratelimit.hits_exceeded"
    ]
    delay: typing.NotRequired[int | float]
    hits: typing.NotRequired[int]


class RateLimitedError(HTTPException):
    def __init__(
        self,
        rule: LimitRule,
        limited_at: datetime,
        reason: str,
        message: str = None,
    ):
        now = utcnow()

        limited_for = math.ceil(
            (
                limited_at + timedelta(seconds=rule.block_time) - now
            ).total_seconds()
        )

        error: ErrorDict = {
            "reason": reason,
            "message": message,
            "limited_for": limited_for,
            "error_type": (
                "ratelimit.delay_exceeded"
                if rule.delay is not None
                else "ratelimit.hits_exceeded"
            ),
        }
        detail = {"error": error}

        if rule.delay is not None:
            error["delay"] = rule.delay

        elif rule.hits is not None:
            error["hits"] = rule.hits

        self.detail = detail
        self.status_code = status.HTTP_429_TOO_MANY_REQUESTS

        self.limited_for = limited_for
        self.limited_at = limited_at
        self.message = message
        self.reason = reason
        self.rule = rule
        self.headers = {"Retry-After": str(limited_for)}
