from uuid import uuid4

import pytest
from pydantic import ValidationError

from sakura_protocol.messages import (
    AttachmentAuth,
    AttachmentCapability,
    Message,
    MessageType,
    Welcome,
    WelcomeCapabilities,
)


def test_message_accepts_sha256_attachments():
    sha256 = "a" * 64
    message = Message(
        message_type=MessageType.MESSAGE_ATTACHMENT,
        sender_aid=uuid4(),
        body="",
        attachments=[sha256],
        is_reply=False,
        reply_seq=0,
        sender_pid="pid",
    )

    assert message.attachments == [sha256]


def test_message_rejects_invalid_attachment_hash():
    with pytest.raises(ValidationError):
        Message(
            message_type=MessageType.MESSAGE_ATTACHMENT,
            sender_aid=uuid4(),
            body="",
            attachments=["not-a-sha256"],
            is_reply=False,
            reply_seq=0,
            sender_pid="pid",
        )


def test_welcome_serializes_attachment_capabilities():
    welcome = Welcome(
        version="0.1.0",
        capabilities=WelcomeCapabilities(
            attachments=AttachmentCapability(
                enabled=True,
                base_url="http://127.0.0.1:21230",
                ttl_seconds=86400,
                max_size_bytes=33554432,
                auth=AttachmentAuth(token="secret"),
            )
        ),
    )

    payload = welcome.model_dump(mode="json")

    assert payload["type"] == "welcome"
    assert payload["capabilities"]["attachments"]["hash"] == "sha256"
    assert payload["capabilities"]["attachments"]["auth"]["token"] == "secret"
