from pydantic import BaseModel


class Error(BaseModel):
    reason: str
    message: str | None
    limited_for: int


class DelayError(Error):
    delay: int | float
    error_type: str = "ratelimit.delay_exceeded"


class HitsError(Error):
    hits: int
    error_type: str = "ratelimit.hits_exceeded"


class RateLimitErrorResponse(BaseModel):
    detail: DelayError | HitsError
