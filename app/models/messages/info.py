from typing import Literal
from uuid import UUID

from app.models.messages.base import MessageBase, MessagePackType


class Info(MessageBase):
    type: Literal[MessagePackType.INFO] = MessagePackType.INFO
    to_aid: UUID
    to_pid: str
    info_type: str  # "info" | "error"
    body: object
