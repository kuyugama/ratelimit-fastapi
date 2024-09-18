from typing import Callable, Coroutine, TYPE_CHECKING
from .user import BaseUser
from .store import BaseStore
from .ranking import BaseRanking

if TYPE_CHECKING:
    from .rule import LimitRule

DEFAULT_BLOCK_TIME: int = 300

ENDPOINT_TTL: int = 3600
USER_TTL: int = 3600
USER_ENDPOINT_TTL: int = 3600


def REASON_BUILDER(rule: "LimitRule") -> str:
    if rule.delay is not None:
        return "Delay between requests exceeded"

    return "Max hits per time exceeded"


AUTHENTICATION_FUNC: Callable[..., BaseUser | Coroutine[None, None, BaseUser]]
RANKING: BaseRanking
STORE: BaseStore
