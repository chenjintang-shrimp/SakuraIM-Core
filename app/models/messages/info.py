from uuid import UUID

from pydantic import BaseModel


class Info(BaseModel):
    to_aid: UUID
    to_pid: int
    type: str
    body: object
