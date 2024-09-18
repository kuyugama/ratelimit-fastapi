from typing import Literal, TYPE_CHECKING, Optional
from dataclasses import dataclass, replace
from contextvars import ContextVar

from .user import BaseUser


if TYPE_CHECKING:
    from .rule import LimitRule


@dataclass(frozen=True)
class _IgnoreData:
    times: int | None = None
    seconds: int | None = None
    level: Literal["authority", "endpoint"] = "authority"
    count_this: bool = False


@dataclass(frozen=True)
class _RankData:
    increase_by: int | None = None
    reset: bool = False


@dataclass(frozen=True)
class _LimitData:
    for_seconds: int | None = None
    message: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _ContextData:
    ignore_data: _IgnoreData | None = None
    rank_data: _RankData | None = None
    limit_data: _LimitData | None = None


class RatelimitContext:
    def __init__(self, rule: Optional["LimitRule"], authority: BaseUser):
        self._data = _ContextData()
        self.rule = replace(rule) if rule else None
        self.authority = authority.model_copy()

    @property
    def data(self):
        return self._data

    def ignore_hit(self):
        self.ignore_user(for_times=1, count_this=True)

    def ignore_user(
        self,
        for_seconds: int | float = None,
        for_times: int = None,
        count_this: bool = False,
    ):
        self._data = replace(
            self._data,
            ignore_data=_IgnoreData(
                for_times, for_seconds, "authority", count_this
            ),
        )

    def ignore_all_users(
        self,
        for_seconds: int | float = None,
        for_times: int = None,
        count_this: bool = False,
    ):
        if count_this and for_times:
            for_times = for_times - 1

        self._data = replace(
            self._data,
            ignore_data=_IgnoreData(
                for_times, for_seconds, "endpoint", count_this
            ),
        )

    def reset_rank(self):
        self._data = replace(
            self._data,
            rank_data=_RankData(reset=True),
        )

    def increase_rank(self, by: int):
        self._data = replace(
            self._data,
            rank_data=_RankData(
                increase_by=by,
            ),
        )

    def limit(
        self,
        for_seconds: int | float | None = None,
        message: str | None = None,
        reason: str | None = None,
    ):
        self._data = replace(
            self._data,
            limit_data=_LimitData(
                for_seconds=for_seconds,
                message=message,
                reason=reason,
            ),
        )


_RatelimitContextContainer: ContextVar[RatelimitContext] = ContextVar(
    "_RatelimitContextContainer"
)


def require_ratelimit_context() -> RatelimitContext:
    context = _RatelimitContextContainer.get(None)
    if not context:
        raise ValueError("Ratelimit context is not set")

    return context
