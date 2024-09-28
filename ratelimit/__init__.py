from typing import Coroutine, Callable
from datetime import timedelta
from logging import getLogger

from fastapi import Depends, Request, FastAPI, HTTPException

from .context import RatelimitContext, require_ratelimit_context
from .response import RateLimitErrorResponse
from .error import RateLimitedError
from .rule import LimitRule
from .user import BaseUser

from .context import _RatelimitContextContainer
from .ranking import BaseRanking
from . import config as _config
from .store import BaseStore
from . import util

__all__ = [
    "require_ratelimit_context",
    "RateLimitErrorResponse",
    "RateLimitedError",
    "RatelimitContext",
    "BaseUser",
    "LimitRule",
    "ratelimit",
]


def __authentication_func_marker__():
    """Placeholder dependency that replaced on ratelimit setup"""
    pass


def setup_ratelimit(
    app: FastAPI,
    ranking: BaseRanking,
    store: BaseStore,
    authentication_func: Callable[
        ..., BaseUser | Coroutine[None, None, BaseUser]
    ],
    reason_builder: Callable[[LimitRule], str] = _config.REASON_BUILDER,
    user_endpoint_ttl: int | float = _config.USER_ENDPOINT_TTL,
    default_block_time: int | float = _config.DEFAULT_BLOCK_TIME,
    user_ttl: int | float = _config.USER_TTL,
    endpoint_ttl: int | float = _config.ENDPOINT_TTL,
    no_hit_on_exceptions: tuple[
        type[Exception], ...
    ] = _config.NO_HIT_ON_EXCEPTIONS,
):

    if util.is_setup():
        raise ValueError("RateLimit already setup")

    if not issubclass(type(ranking), BaseRanking):
        raise TypeError(
            "Ranking must be an instance of subclass of BaseRanking"
        )

    if not issubclass(type(store), BaseStore):
        raise TypeError("Store must be an instance of subclass of BaseStore")

    if not callable(authentication_func):
        raise TypeError("Authority function must be callable")

    app.dependency_overrides[__authentication_func_marker__] = (
        authentication_func
    )

    _config.NO_HIT_ON_EXCEPTIONS = no_hit_on_exceptions
    _config.USER_ENDPOINT_TTL = int(user_endpoint_ttl)
    _config.DEFAULT_BLOCK_TIME = int(default_block_time)
    _config.USER_TTL = int(user_ttl)
    _config.ENDPOINT_TTL = int(endpoint_ttl)
    _config.REASON_BUILDER = reason_builder
    _config.RANKING = ranking
    _config.STORE = store


def ratelimit(
    *ranks: tuple[LimitRule, ...] | LimitRule,
    no_block_delay: bool = True,
    no_hit_on_exceptions: tuple[type[Exception], ...] = None,
    use_raw_path: bool = False,
):
    """
    Ratelimit dependency
    :param ranks: Limit ranks
    :param no_block_delay: No block at rules with "delay" set
    :param use_raw_path: Use endpoint raw path
    :return: Actual dependency
    """

    async def dependency(
        request: Request,
        context_user: BaseUser = Depends(__authentication_func_marker__),
    ) -> None:
        nonlocal no_block_delay, no_hit_on_exceptions

        if not util.is_setup():
            raise ValueError("RateLimit is not setup")

        if no_hit_on_exceptions is None:
            no_hit_on_exceptions = _config.NO_HIT_ON_EXCEPTIONS

        ranking = _config.RANKING
        store = _config.STORE

        log = getLogger("ratelimit.dependency")
        now = util.utcnow()

        user = await ranking.get_user(context_user.unique_id)
        if not user:
            user = context_user

        path = request.url.path
        if use_raw_path:
            path = (
                request.scope.get("root_path")
                + request.scope.get("route").path_format
            )
        method = request.method

        log.debug(
            f"Incoming {method} request for {path} "
            f"from UID {user.unique_id}",
            extra={"user": user, "path": path, "method": method},
        )

        user_endpoint = await store.get_user_endpoint(
            path, method, user.unique_id
        )
        endpoint = await store.get_endpoint(path, method)

        if user_endpoint.blocked:
            log.debug(
                f"Blocked incoming {method} request for {path} "
                f"from UID {user.unique_id}",
                extra={
                    "path": path,
                    "method": method,
                    "user": user,
                    "blocked_by_rule": user_endpoint.blocked_by_rule,
                },
            )
            raise RateLimitedError(
                user_endpoint.blocked_by_rule,
                user_endpoint,
                user_endpoint.blocked_at,
                user_endpoint.blocked_by_rule.reason
                or _config.REASON_BUILDER(user_endpoint.blocked_by_rule),
                user_endpoint.blocked_by_rule.message,
            )

        if user.rank >= len(ranks):
            rules = ranks[-1]
        else:
            rules = ranks[user.rank]

        user_endpoint.hits.append(now)

        rule = None

        try:
            # Get the rule which user exceed
            rule = util.get_exceeded_rule(
                rules, endpoint, user_endpoint, user.group
            )

            user_endpoint.hits = user_endpoint.hits[-util.get_max_hits(rules) :]

            if rule is not None:
                # Increase user rank if needed
                if rule.increase_rank:
                    user.rank = min(user.rank + 1, len(ranks))
                    await ranking.save_user(user)
                    log.debug(
                        f"Increase rank for UID {user.unique_id} "
                        f"for {method} requests at {path}",
                        extra={
                            "rule": rule,
                            "path": path,
                            "method": method,
                            "user": user,
                            "endpoint": user_endpoint,
                        },
                    )

                if not (rule.delay is not None and no_block_delay):
                    # Set the rule user is limited by
                    user_endpoint.blocked_by_rule = rule
                    user_endpoint.blocked_at = now
                    log.debug(
                        f"Rate-limit UID {user.unique_id} "
                        f"for {method} requests at {path}",
                        extra={
                            "rule": rule,
                            "path": path,
                            "method": method,
                            "user": user,
                            "endpoint": user_endpoint,
                        },
                    )

                else:
                    # Remove this hit to prevent loops
                    user_endpoint.hits = user_endpoint.hits[:-1]

            # Save endpoints in case of existing rule or not
            await store.save_user_endpoint(user_endpoint, user)

            # If rule require delay between requests
            # - we need raise user error immediately without processing endpoint
            if rule is not None and rule.delay is not None:
                log.debug(
                    "Immediately forbid endpoint processing "
                    f"for UID {user.unique_id} for {method} request at {path}",
                    extra={
                        "rule": rule,
                        "path": path,
                        "method": method,
                        "user": user,
                        "endpoint": user_endpoint,
                    },
                )
                raise RateLimitedError(
                    rule,
                    user_endpoint,
                    now,
                    _config.REASON_BUILDER(rule),
                    rule.message,
                    options={"no_block_delay": no_block_delay},
                )

        except util.Ignore as e:
            user_endpoint.hits.clear()
            log.debug(
                f"Ignore incoming {method} request for {path}",
                extra={
                    "path": path,
                    "method": method,
                    "user": user,
                    "endpoint": (
                        user_endpoint if e.context == "user" else endpoint
                    ),
                    "context": e.context,
                },
            )
            if isinstance(e, util.IgnoreByCount):
                if e.context == "user":
                    user_endpoint.ignore_times -= 1
                    await store.save_user_endpoint(user_endpoint, user)
                elif e.context == "endpoint":
                    endpoint.ignore_times -= 1
                    await store.save_endpoint(endpoint)

        ctx = RatelimitContext(rule, user, user_endpoint)

        token = _RatelimitContextContainer.set(ctx)

        try:
            yield
        except Exception as e:
            # Hit on HTTPException by default
            if (
                isinstance(e, HTTPException)
                and HTTPException not in no_hit_on_exceptions
            ):
                raise

            if (
                isinstance(e, no_hit_on_exceptions)
                and now in user_endpoint.hits
            ):
                user_endpoint.hits.remove(now)
                await store.save_user_endpoint(user_endpoint, user)
            raise

        _RatelimitContextContainer.reset(token)

        log.debug(
            f"Processing {method} {path} context",
            extra={
                "path": path,
                "method": method,
                "user": user,
                "endpoint": user_endpoint,
                "context": ctx.data,
            },
        )

        if ctx.data.ignore_data is not None:
            data = ctx.data.ignore_data

            if data.times:
                for_ = f"{data.times} times"
            else:
                for_ = f"{data.seconds} seconds"

            if data.level == "endpoint":
                endpoint.ignore_times = data.times
                endpoint.ignore_until = (
                    now + timedelta(seconds=data.seconds)
                    if data.seconds
                    else None
                )

                await store.save_endpoint(endpoint)

                if data.count_this and now in user_endpoint.hits:
                    user_endpoint.hits.remove(now)
                    await store.save_user_endpoint(user_endpoint, user)

                log.debug(
                    f"Ignore new {method} requests for {path} "
                    f"from everyone for {for_}",
                    extra={
                        "path": path,
                        "method": method,
                        "user": user,
                        "endpoint": endpoint,
                        "times": data.times,
                        "seconds": data.seconds,
                    },
                )

            elif data.level == "user":
                user_endpoint.ignore_times = data.times
                user_endpoint.ignore_until = (
                    now + timedelta(seconds=data.seconds)
                    if data.seconds
                    else None
                )

                if data.count_this and now in user_endpoint.hits:
                    user_endpoint.hits.remove(now)

                await store.save_user_endpoint(user_endpoint, user)

                log.debug(
                    f"Ignore new {method} requests for {path} "
                    f"from UID {user.unique_id} for {for_}",
                    extra={
                        "path": path,
                        "method": method,
                        "user": user,
                        "endpoint": user_endpoint,
                        "times": data.times,
                        "seconds": data.seconds,
                    },
                )

        if ctx.data.rank_data is not None:
            data = ctx.data.rank_data

            if data.reset:
                user.rank = 0
                log.debug(
                    f"Reset rank for UID {user.unique_id} "
                    f"for {method} requests at {path}",
                    extra={
                        "path": path,
                        "method": method,
                        "user": user,
                        "endpoint": user_endpoint,
                    },
                )
            elif data.increase_by:
                user.rank = max(user.rank + data.increase_by, 0)
                log.debug(
                    f"Increase rank by {data.increase_by} for UID {user.unique_id} "
                    f"for {method} requests at {path}",
                    extra={
                        "path": path,
                        "method": method,
                        "user": user,
                        "endpoint": user_endpoint,
                        "increase_by": data.increase_by,
                    },
                )

            await ranking.save_user(user)

        if ctx.data.limit_data is not None:
            data = ctx.data.limit_data

            block_time = data.for_seconds
            if block_time is None and rules:
                if isinstance(rules, tuple):
                    rules = rules[0]

                block_time = rules.block_time

            elif block_time is None:
                block_time = _config.DEFAULT_BLOCK_TIME

            rule = LimitRule(
                hits=1,
                batch_time=1,
                message=data.message,
                reason=data.reason,
                block_time=block_time,
            )

            log.debug(
                f"Rate-limit UID {user.unique_id} "
                f"for {block_time} seconds for {method} requests at {path}",
                extra={
                    "rule": rule,
                    "path": path,
                    "method": method,
                    "user": user,
                    "block_time": block_time,
                    "endpoint": user_endpoint,
                },
            )

            user_endpoint.blocked_by_rule = rule
            user_endpoint.blocked_at = now
            await store.save_user_endpoint(user_endpoint, user)

        log.debug(f"Processing of {method} {path} complete")

    return dependency
