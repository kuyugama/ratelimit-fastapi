from abc import abstractmethod, ABC
from datetime import datetime
import uuid

from pydantic import BaseModel, Field, computed_field

UserID = int | float | str | uuid.UUID


class BaseUser(BaseModel, ABC):
    group: str
    rank: int = Field(default=0, ge=0, le=100)

    @computed_field
    @abstractmethod
    def unique_id(self) -> UserID:
        """Unique id that will be used to identify user"""
        ...
