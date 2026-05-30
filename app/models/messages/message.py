from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.messages.base import MessagePackType


class MessageType(StrEnum):
    MESSAGE_NORMAL = "normal"
    MESSAGE_ATTACHMENT = "attachment"
    MESSAGE_REACTION = "reaction"


class Message(BaseModel):
    type: Literal[MessagePackType.MESSAGE]
    message_type: MessageType
    sender_aid: UUID
    body: str
    attachments: bytes
    is_reply: bool
    reply_seq: int
    sender_pid: str
