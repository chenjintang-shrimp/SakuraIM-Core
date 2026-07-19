from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError

from sakura_core.configs import get_settings
from sakura_core.core.adapter_tokens import (
    issue_adapter_token,
    revoke_adapter_token,
    verify_adapter_token,
)
from sakura_core.core.command_handles import dispatch_command
from sakura_core.core.connection_manager import AdapterSession, manager
from sakura_core.core.global_indexes import get_global_indexes
from sakura_core.db import AsyncSessionLocal
from sakura_core.models import Adapter
from sakura_protocol.messages import (
    Ack,
    AttachmentAuth,
    AttachmentCapability,
    Command,
    Info,
    Message,
    Welcome,
    WelcomeCapabilities,
)
from sakura_protocol.messages.base import MessagePackType
from sakura_protocol.messages.hello import Hello

router = APIRouter(prefix="/adapter", tags=["adapter"])
internal_router = APIRouter(prefix="/internal/oss", tags=["internal-oss"])
settings = get_settings()


class VerifyTokenRequest(BaseModel):
    token: str


@internal_router.post("/verify-token", status_code=204)
async def verify_oss_token(request: VerifyTokenRequest) -> None:
    if not await verify_adapter_token(request.token):
        raise HTTPException(status_code=401, detail="invalid token")


async def _sender_task(websocket: WebSocket, aid_str: str, outbox: asyncio.Queue) -> None:
    """从出站队列取消息并发送给 WebSocket 对端。收到 None 时退出。"""
    try:
        while True:
            msg = await outbox.get()
            if msg is None:
                break
            try:
                await websocket.send_json(msg.model_dump(mode="json"))
            except Exception as e:
                logger.warning(f"[{aid_str}] send failed: {e}")
                break
    except asyncio.CancelledError:
        pass


@router.websocket("/ws")
async def dispatch_messages(connection: WebSocket):
    await connection.accept()

    aid = None
    platform = None
    sender = None
    session: AdapterSession | None = None

    try:
        # ── 握手阶段 ──────────────────────────────────────────────
        try:
            payload = await connection.receive_json()
            hello = Hello.model_validate(payload)
        except ValidationError as e:
            assert connection.client is not None
            logger.error(
                f"Bad Hello from {connection.client.host}:{connection.client.port}: {e}"
            )
            await connection.close(code=1008)
            return

        aid = hello.aid
        platform = hello.platform
        aid_str = str(aid)

        # 持久化 Adapter（首次注册时写 DB；已存在则更新 platform）
        async with AsyncSessionLocal() as db_session:
            existing = await db_session.get(Adapter, aid)
            if existing is None:
                db_session.add(Adapter(aid=aid, platform=platform))
                await db_session.commit()
                logger.info(f"[{aid_str}] new adapter registered to DB (platform={platform})")
            elif existing.platform != platform:
                logger.warning(
                    f"[{aid_str}] platform changed: {existing.platform} -> {platform}"
                )
                existing.platform = platform
                db_session.add(existing)
                await db_session.commit()

        # 加入连接池，拿到 AdapterSession（含 outbox）
        session = await manager.register_connection(connection, aid)

        # 启动后台发送任务
        sender = asyncio.create_task(
            _sender_task(connection, aid_str, session.outbox)
        )

        # 更新内存索引
        indexes = get_global_indexes()
        indexes.add_adapter(aid, platform)

        adapter_token = await issue_adapter_token(aid)
        await manager.send_to(
            aid,
            Welcome(
                version="0.1.0",
                capabilities=WelcomeCapabilities(
                    attachments=AttachmentCapability(
                        enabled=settings.oss_enabled,
                        base_url=settings.oss_base_url,
                        ttl_seconds=settings.oss_ttl_seconds,
                        max_size_bytes=settings.oss_max_size_bytes,
                        auth=AttachmentAuth(token=adapter_token)
                        if settings.oss_enabled
                        else None,
                    )
                ),
            ),
        )

        logger.info(f"[{aid_str}] handshake complete (platform={platform})")

        # ── 消息主循环 ────────────────────────────────────────────
        while True:
            try:
                data = await connection.receive_json()
            except WebSocketDisconnect:
                logger.info(f"[{aid_str}] disconnected")
                break

            msg_type = data.get("type")

            # --- 普通消息转发 ---
            if msg_type == MessagePackType.MESSAGE:
                try:
                    msg = Message.model_validate(data)
                except ValidationError as e:
                    logger.warning(f"[{aid_str}] invalid Message packet: {e}")
                    await manager.send_to(aid, Info(
                        to_aid=aid, to_pid="",
                        info_type="error",
                        body={"error_type": "invalid_packet", "detail": str(e)}
                    ))
                    continue

                # 反查发送者 uid
                sender_user = indexes.get_user(msg.sender_pid, platform)
                if sender_user is None:
                    logger.warning(f"[{aid_str}] message from unbound pid={msg.sender_pid}")
                    await manager.send_to(aid, Info(
                        to_aid=aid, to_pid=msg.sender_pid,
                        info_type="error",
                        body={"error_type": "user_not_bound"}
                    ))
                    continue

                target = indexes.get_target(sender_user.uid, aid)
                if target is None:
                    logger.warning(
                        f"[{aid_str}] no session for uid={sender_user.uid}"
                    )
                    await manager.send_to(aid, Info(
                        to_aid=aid, to_pid=msg.sender_pid,
                        info_type="error",
                        body={"error_type": "no_active_session"}
                    ))
                    continue

                _, target_aid = target
                ok = await manager.send_to(target_aid, msg)
                if not ok:
                    logger.warning(
                        f"[{aid_str}] failed to forward message to adapter {target_aid}"
                    )

            # --- 指令分发 ---
            elif msg_type == MessagePackType.COMMAND:
                try:
                    cmd = Command.model_validate(data)
                except ValidationError as e:
                    logger.warning(f"[{aid_str}] invalid Command packet: {e}")
                    await manager.send_to(aid, Info(
                        to_aid=aid, to_pid="",
                        info_type="error",
                        body={"error_type": "invalid_packet", "detail": str(e)}
                    ))
                    continue

                await dispatch_command(cmd)

            # --- Ack 消息确认处理 ---
            elif msg_type == MessagePackType.ACK:
                try:
                    ack = Ack.model_validate(data)
                except ValidationError as e:
                    logger.warning(f"[{aid_str}] invalid Ack packet: {e}")
                    # Use the platform-specific pid from the session context if available
                    # For ACK errors, we don't have a specific sender_pid, so use empty string
                    # but this could be improved by tracking the last known pid per adapter
                    await manager.send_to(aid, Info(
                        to_aid=aid, to_pid="",
                        info_type="error",
                        body={"error_type": "invalid_packet", "detail": str(e)}
                    ))
                    continue

                # ACK 处理逻辑：记录已确认的消息序列号，用于可靠投递
                # 目前实现为简单的日志记录，后续可扩展为重传机制
                logger.debug(f"[{aid_str}] received ack for seq={ack.ack_seq}")

            # --- 未知类型 ---
            else:
                logger.warning(f"[{aid_str}] unknown message type: {msg_type!r}")
                await manager.send_to(aid, Info(
                    to_aid=aid, to_pid="",
                    info_type="error",
                    body={"error_type": "unknown_message_type", "type": msg_type}
                ))

    except Exception as e:
        logger.exception(f"[{aid}] unexpected error in dispatch_messages: {e}")
        try:
            await connection.close(code=1011)
        except Exception:
            pass

    finally:
        # 清理：取消发送任务、注销连接、更新内存索引
        if sender is not None and session is not None:
            await session.outbox.put(None)  # 让 sender_task 优雅退出
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass

        if aid is not None:
            if session is not None:
                removed = await manager.deregister_connection(aid, session)
                if removed:
                    await revoke_adapter_token(aid)
                    indexes = get_global_indexes()
                    indexes.remove_adapter(aid)
                    logger.info(f"[{aid}] cleaned up")
