from enum import StrEnum
from typing import Literal
from uuid import UUID

from sakura_protocol.messages.base import MessageBase, MessagePackType


class MessageType(StrEnum):
    MESSAGE_NORMAL = "normal"
    MESSAGE_ATTACHMENT = "attachment"
    MESSAGE_REACTION = "reaction"


class Message(MessageBase):
    type: Literal[MessagePackType.MESSAGE] = MessagePackType.MESSAGE
    message_type: MessageType
    sender_aid: UUID
    body: str
    attachments: bytes
    is_reply: bool
    reply_seq: int
    sender_pid: str
