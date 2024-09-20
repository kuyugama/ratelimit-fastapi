from typing import Coroutine, Callable
from datetime import timedelta
from logging import getLogger

from fastapi import Depends, Request, FastAPI

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

    _config.USER_ENDPOINT_TTL = int(user_endpoint_ttl)
    _config.DEFAULT_BLOCK_TIME = int(default_block_time)
    _config.USER_TTL = int(user_ttl)
    _config.ENDPOINT_TTL = int(endpoint_ttl)
    _config.REASON_BUILDER = reason_builder
    _config.RANKING = ranking
    _config.STORE = store


def ratelimit(*ranks: tuple[LimitRule, ...] | LimitRule):
    async def dependency(
        request: Request,
        context_authority: BaseUser = Depends(__authentication_func_marker__),
    ) -> None:
        if not util.is_setup():
            raise ValueError("RateLimit is not setup")

        ranking = _config.RANKING
        store = _config.STORE

        log = getLogger("ratelimit.dependency")
        now = util.utcnow()

        authority = await ranking.get_user(context_authority.unique_id)
        if not authority:
            authority = context_authority

        path = request.url.path
        method = request.method

        log.debug(
            f"Incoming {method} request for {path} "
            f"from UID {authority.unique_id}",
            extra={"authority": authority, "path": path, "method": method},
        )

        authority_endpoint = await store.get_user_endpoint(
            path, method, authority.unique_id
        )
        endpoint = await store.get_endpoint(path, method)

        if authority_endpoint.blocked:
            log.debug(
                f"Blocked incoming {method} request for {path} "
                f"from UID {authority.unique_id}",
                extra={
                    "path": path,
                    "method": method,
                    "authority": authority,
                    "blocked_by_rule": authority_endpoint.blocked_by_rule,
                },
            )
            raise RateLimitedError(
                authority_endpoint.blocked_by_rule,
                authority_endpoint.blocked_at,
                authority_endpoint.blocked_by_rule.reason
                or _config.REASON_BUILDER(authority_endpoint.blocked_by_rule),
                authority_endpoint.blocked_by_rule.message,
            )

        if authority.rank >= len(ranks):
            rules = ranks[-1]
        else:
            rules = ranks[authority.rank]

        authority_endpoint.hits.append(now)

        rule = None

        try:
            # Get the rule which user exceed
            rule = util.get_exceeded_rule(
                rules, endpoint, authority_endpoint, authority.group
            )

            authority_endpoint.hits = authority_endpoint.hits[
                -util.get_max_hits(rules) :
            ]

            if rule is not None:
                # Increase user rank if needed
                if rule.increase_rank:
                    authority.rank = min(authority.rank + 1, len(ranks))
                    await ranking.save_user(authority)
                    log.debug(
                        f"Increase rank for UID {authority.unique_id} "
                        f"for {method} requests at {path}",
                        extra={
                            "rule": rule,
                            "path": path,
                            "method": method,
                            "authority": authority,
                            "endpoint": authority_endpoint,
                        },
                    )

                # Set the rule user is limited by
                authority_endpoint.blocked_by_rule = rule
                authority_endpoint.blocked_at = now
                log.debug(
                    f"Rate-limit UID {authority.unique_id} "
                    f"for {method} requests at {path}",
                    extra={
                        "rule": rule,
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": authority_endpoint,
                    },
                )

            # Save endpoints in case of existing rule or not
            await store.save_user_endpoint(authority_endpoint, authority)

            # If rule require delay between requests
            # - we need raise user error immediately without processing endpoint
            if rule is not None and rule.delay is not None:
                log.debug(
                    "Immediately forbid endpoint processing "
                    f"for UID {authority.unique_id} for {method} request at {path}",
                    extra={
                        "rule": rule,
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": authority_endpoint,
                    },
                )
                raise RateLimitedError(
                    rule,
                    now,
                    _config.REASON_BUILDER(rule),
                    rule.message,
                )

        except util.Ignore as e:
            authority_endpoint.hits.clear()
            log.debug(
                f"Ignore incoming {method} request for {path}",
                extra={
                    "path": path,
                    "method": method,
                    "authority": authority,
                    "endpoint": (
                        authority_endpoint
                        if e.context == "authority"
                        else endpoint
                    ),
                    "context": e.context,
                },
            )
            if isinstance(e, util.IgnoreByCount):
                if e.context == "authority":
                    authority_endpoint.ignore_times -= 1
                    await store.save_user_endpoint(
                        authority_endpoint, authority
                    )
                elif e.context == "endpoint":
                    endpoint.ignore_times -= 1
                    await store.save_endpoint(endpoint)

        ctx = RatelimitContext(rule, authority)

        token = _RatelimitContextContainer.set(ctx)

        yield

        _RatelimitContextContainer.reset(token)

        log.debug(
            f"Processing {method} {path} context",
            extra={
                "path": path,
                "method": method,
                "authority": authority,
                "endpoint": authority_endpoint,
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

                if data.count_this and now in authority_endpoint.hits:
                    authority_endpoint.hits.remove(now)
                    await store.save_user_endpoint(
                        authority_endpoint, authority
                    )

                log.debug(
                    f"Ignore new {method} requests for {path} "
                    f"from everyone for {for_}",
                    extra={
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": endpoint,
                        "times": data.times,
                        "seconds": data.seconds,
                    },
                )

            elif data.level == "authority":
                authority_endpoint.ignore_times = data.times
                authority_endpoint.ignore_until = (
                    now + timedelta(seconds=data.seconds)
                    if data.seconds
                    else None
                )

                if data.count_this and now in authority_endpoint.hits:
                    authority_endpoint.hits.remove(now)

                await store.save_user_endpoint(authority_endpoint, authority)

                log.debug(
                    f"Ignore new {method} requests for {path} "
                    f"from UID {authority.unique_id} for {for_}",
                    extra={
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": authority_endpoint,
                        "times": data.times,
                        "seconds": data.seconds,
                    },
                )

        if ctx.data.rank_data is not None:
            data = ctx.data.rank_data

            if data.reset:
                authority.rank = 0
                log.debug(
                    f"Reset rank for UID {authority.unique_id} "
                    f"for {method} requests at {path}",
                    extra={
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": authority_endpoint,
                    },
                )
            elif data.increase_by:
                authority.rank = max(authority.rank + data.increase_by, 0)
                log.debug(
                    f"Increase rank by {data.increase_by} for UID {authority.unique_id} "
                    f"for {method} requests at {path}",
                    extra={
                        "path": path,
                        "method": method,
                        "authority": authority,
                        "endpoint": authority_endpoint,
                        "increase_by": data.increase_by,
                    },
                )

            await ranking.save_user(authority)

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
                f"Rate-limit UID {authority.unique_id} "
                f"for {block_time} seconds for {method} requests at {path}",
                extra={
                    "rule": rule,
                    "path": path,
                    "method": method,
                    "authority": authority,
                    "block_time": block_time,
                    "endpoint": authority_endpoint,
                },
            )

            authority_endpoint.blocked_by_rule = rule
            authority_endpoint.blocked_at = now
            await store.save_user_endpoint(authority_endpoint, authority)

        log.debug(f"Processing of {method} {path} complete")

    return dependency
