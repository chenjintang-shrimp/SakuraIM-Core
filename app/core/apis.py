from fastapi import APIRouter, WebSocket
from loguru import logger

from app.db import SessionDep
from app.models.adapters import Adapter

router = APIRouter(prefix="/adapter", tags=["adapter"])


@router.websocket("/ws")
async def dispatch_messages(connection: WebSocket):
    await connection.accept()
    platform
