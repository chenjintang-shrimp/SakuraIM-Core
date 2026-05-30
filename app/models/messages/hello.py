from uuid import UUID

from pydantic import BaseModel


class Hello(BaseModel):
    aid: UUID
    platform: str
