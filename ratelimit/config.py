from typing import TYPE_CHECKING

from .ranking import BaseRanking
from .store import BaseStore

if TYPE_CHECKING:
    from .rule import LimitRule

DEFAULT_BLOCK_TIME: int = 300

ENDPOINT_TTL: int = 3600
USER_TTL: int = 3600
USER_ENDPOINT_TTL: int = 3600

NO_HIT_ON_EXCEPTIONS: tuple[type[Exception], ...] = ()


def REASON_BUILDER(rule: "LimitRule") -> str:
    if rule.delay is not None:
        return "Delay between requests exceeded"

    return "Max hits per time exceeded"


RANKING: BaseRanking
STORE: BaseStore
