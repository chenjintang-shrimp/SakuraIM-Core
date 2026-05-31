from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.messages.base import MessageBase, MessagePackType


class Info(MessageBase):
    type: Literal[MessagePackType.INFO] = MessagePackType.INFO
    to_aid: UUID
    to_pid: str
    type: str
    body: object
