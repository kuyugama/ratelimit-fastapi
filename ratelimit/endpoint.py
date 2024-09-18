from datetime import datetime, timedelta

from pydantic import BaseModel, computed_field

from .rule import LimitRule


class Endpoint(BaseModel):
    path: str
    method: str
    hits: list[datetime] = []

    ignore_times: int | None = None
    ignore_until: datetime | None = None

    blocked_at: datetime | None = None
    blocked_by_rule: LimitRule | None = None

    @computed_field
    def blocked(self) -> bool:
        from . import util

        return (
            self.blocked_by_rule is not None
            and self.blocked_at
            + timedelta(seconds=self.blocked_by_rule.block_time)
            > util.utcnow()
        )
