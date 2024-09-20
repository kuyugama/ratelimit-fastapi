from typing import Literal
import datetime

from .endpoint import Endpoint
from .rule import LimitRule
from . import config


class Ignore(BaseException):
    def __init__(self, context: Literal["endpoint", "authority"]):
        self.context = context


class IgnoreByCount(Ignore):
    pass


class IgnoreByTime(Ignore):
    pass


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def get_exceeded_rule(
    rules: LimitRule | tuple[LimitRule, ...],
    endpoint: Endpoint,
    authority_endpoint: Endpoint,
    group: str,
) -> LimitRule | None:
    now = utcnow()

    rules = get_rules_for_group(rules, group)

    if endpoint.ignore_times is not None and endpoint.ignore_times > 0:
        raise IgnoreByCount("endpoint")

    elif (
        authority_endpoint.ignore_times is not None
        and authority_endpoint.ignore_times > 0
    ):
        raise IgnoreByCount("authority")

    if endpoint.ignore_until is not None and endpoint.ignore_until >= now:
        raise IgnoreByTime("endpoint")

    elif (
        authority_endpoint.ignore_until is not None
        and authority_endpoint.ignore_until >= now
    ):
        raise IgnoreByTime("authority")

    for rule in rules:
        hits = authority_endpoint.hits

        if rule.hits is not None:
            min_hit_time = now - datetime.timedelta(seconds=rule.batch_time)

            # If there are more hits than allowed in that group of hits
            if (
                len(
                    list(
                        filter(lambda hit_time: hit_time >= min_hit_time, hits)
                    )
                )
                >= rule.hits
            ):
                return rule

        if rule.delay is not None:
            if len(hits) < 2:
                continue

            # If delay between two last requests is less than required delay
            if (hits[-1] - hits[-2]).total_seconds() < rule.delay:
                return rule


def get_max_hits(rules: LimitRule | tuple[LimitRule, ...]) -> int:
    if isinstance(rules, LimitRule):
        if rules.delay is not None:
            return 2

        else:
            return rules.hits

    if len(rules) == 0:
        return 0

    return get_max_hits(max(rules, key=get_max_hits))


def get_rules_for_group(
    rules: LimitRule | tuple[LimitRule, ...], group: str
) -> tuple[LimitRule, ...]:
    if isinstance(rules, LimitRule):
        rules = (rules,)

    return tuple(
        rule
        for rule in rules
        if rule.affected_group is None
        or (
            isinstance(rule.affected_group, list)
            and group in rule.affected_group
        )
        or rule.affected_group == group
    )


def is_setup() -> bool:
    return hasattr(config, "STORE") and hasattr(config, "RANKING")
