from dataclasses import dataclass

from . import config as _config


@dataclass(frozen=True)
class LimitRule:
    hits: int | None = None
    """Max number of requests per endpoint per time"""
    batch_time: int | float | None = None
    """The time taken into account when processing the 
    maximum number of requests to the endpoint"""
    delay: int | float | None = None
    """Delay in seconds between requests"""
    block_time: int | float = _config.DEFAULT_BLOCK_TIME
    """The time for what will user be blocked in seconds"""

    increase_rank: bool = True
    """Whether to increase user rank if limiting rule was exceeded"""
    message: str | None = None
    """Message to be returned to the client if limiting rule was exceeded"""
    reason: str | None = None
    """Message to be returned to the client in "reason" field 
    if limiting rule was exceeded"""

    affected_group: str | list[str] | None = None
    """Group on which this rule affects. Defaults to all groups"""

    def __post_init__(self):
        if self.hits is None and self.batch_time is None and self.delay is None:
            raise ValueError(
                "If 'delay' is None then 'hits' and 'batch_time' must not be None"
            )

        if self.hits is not None and self.batch_time is None:
            raise ValueError(
                "If 'hits' is None then 'batch_time' must not be None"
            )

        if (
            self.hits is not None or self.batch_time is not None
        ) and self.delay is not None:
            raise ValueError(
                "If 'delay' is not None then 'hits' and 'batch_time' must be None"
            )

        if self.delay is not None and self.delay <= 0:
            raise ValueError("'delay' must be greater than zero")

        if self.hits is not None and self.hits <= 0:
            raise ValueError("'hits' must be greater than zero")

        if self.batch_time is not None and self.batch_time <= 0:
            raise ValueError("'batch_time' must be greater than zero")

        if (
            self.affected_group is not None
            and not isinstance(self.affected_group, list)
            and not isinstance(self.affected_group, str)
        ):
            raise ValueError(
                "'affected_group' must be a string or a list of strings"
            )

        if (
            isinstance(self.affected_group, list)
            and len(self.affected_group) == 0
        ):
            raise ValueError("'affected_group' cannot be an empty list")
