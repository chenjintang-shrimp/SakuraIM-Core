from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import ValidationError

from sakura_core.core.command_handles import dispatch_command
from sakura_core.core.connection_manager import manager
from sakura_core.core.global_indexes import get_global_indexes
from sakura_core.db import AsyncSessionLocal
from sakura_core.models import Adapter
from sakura_protocol.messages import Command, Info, Message
from sakura_protocol.messages.base import MessagePackType
from sakura_protocol.messages.hello import Hello

router = APIRouter(prefix="/adapter", tags=["adapter"])


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

        # 更新内存索引
        indexes = get_global_indexes()
        indexes.add_adapter(aid, platform)

        # 加入连接池，拿到 AdapterSession（含 outbox）
        session = await manager.register_connection(connection, aid)

        # 启动后台发送任务
        sender = asyncio.create_task(
            _sender_task(connection, aid_str, session.outbox)
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

            # --- Ack（预留，暂不处理）---
            elif msg_type == MessagePackType.ACK:
                pass

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
        if sender is not None:
            await session.outbox.put(None)  # 让 sender_task 优雅退出
            sender.cancel()
            try:
                await sender
            except asyncio.CancelledError:
                pass

        if aid is not None:
            await manager.deregister_connection(aid)
            indexes = get_global_indexes()
            indexes.remove_adapter(aid)
            logger.info(f"[{aid}] cleaned up")
