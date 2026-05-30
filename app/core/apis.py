import json
import platform

from fastapi import APIRouter, WebSocket
from loguru import logger
from pydantic import ValidationError

from app.db import SessionDep
from app.models.adapters import Adapter
from app.models.messages import Hello

router = APIRouter(prefix="/adapter", tags=["adapter"])


@router.websocket("/ws")
async def dispatch_messages(connection: WebSocket):
    await connection.accept()
    session = None
    aid = None
    try:
        payload = await connection.receive_json()
        message = Hello.model_validate(payload)
        aid = message.aid
        platform = message.platform

    except ValidationError:
        assert connection.client is not None  # 毋庸置疑！
        logger.error(
            f"Caught adapter from {connection.client.host}:{connection.client.port} does not send right hello message"
        )
        await connection.close(code=1008)
