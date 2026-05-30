from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class MessageType(StrEnum):
    MESSAGE_NORMAL = "normal"
    MESSAGE_ATTACHMENT = "attachment"
    MESSAGE_REACTION = "reaction"


class Message(BaseModel):
    message_type: MessageType
    sender_aid: UUID
    body: str
    attachments: bytes
    is_reply: bool
    reply_seq: int
    sender_pid: str
