# SakuraIM

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-core-green)](https://fastapi.tiangolo.com/)
[![uv](https://img.shields.io/badge/workspace-uv-purple)](https://docs.astral.sh/uv/)

[English](README.en.md)

SakuraIM 是一个面向多平台 adapter 的消息中继核心。它不试图成为新的聊天客户端，也不替任何平台保存完整的聊天历史；它更像一个轻量的路由层，把不同平台上的用户绑定到统一的 SakuraIM 用户身份，再把会话里的消息转发到合适的 adapter。

项目目前由三个 workspace package 组成。`sakura-protocol` 定义 adapter 和 core 之间共享的 Pydantic 消息模型，`sakura-core` 负责 WebSocket 接入、用户绑定、会话管理和消息路由，`sakura-oss` 则提供一个临时附件缓存服务，用来中转 emoji、语音、贴纸、照片这类聊天媒体。

adapter 连接 core 后，会先发送 `hello`。core 完成握手后返回 `welcome`，其中包含当前 core 的能力信息。如果附件缓存启用，`welcome` 会告诉 adapter OSS 服务地址、TTL、大小限制、hash 算法以及本次连接可用的 bearer token。这个 token 按 adapter 的 `aid` 生成，hash 存在 core 自己的 SQLite 中，adapter 下线后会被撤销。

附件不会直接塞进消息体。adapter 发送附件前先计算文件 bytes 的 SHA-256，通过 Sakura OSS 的 `HEAD /objects/{sha256}` 检查对象是否存在，缺失时用 `PUT /objects/{sha256}` 上传。之后消息里的 `attachments` 字段只引用 sha256 字符串。接收方 adapter 再用自己的 token 通过 `GET /objects/{sha256}` 下载对象。Sakura OSS 是临时缓存，默认 TTL 为一天，不承诺长期保存。

本仓库使用 Python 3.12 和 uv workspace。安装依赖后可以分别启动 core 和 OSS 服务：

```powershell
uv sync
uv run uvicorn sakura_core.main:app --host 0.0.0.0 --port 21229
uv run uvicorn sakura_oss.main:app --host 0.0.0.0 --port 21230
```

core 默认使用 `sqlite+aiosqlite:///./data/app.db`，OSS 默认使用 `sqlite+aiosqlite:///./data/oss.db`，对象文件默认写入 `./data/objects`。这些值可以通过 `.env` 覆盖。core 侧配置使用 `OSS_BASE_URL`、`OSS_TTL_SECONDS`、`OSS_MAX_SIZE_BYTES` 等变量；OSS 服务自身配置使用 `OSS_DATABASE_URL`、`OSS_OBJECT_ROOT`、`OSS_CORE_VERIFY_URL` 等变量，避免和 core 的数据库配置混用。

adapter 实现者可以从 [Adapter Protocol](docs/adapter-spec.md) 开始。那份文档描述了 WebSocket 包格式、`hello`/`welcome` 握手、命令、消息、附件上传下载流程和 token 生命周期。

开发时可以运行测试和静态检查：

```powershell
uv run pytest -q
uv run ruff check packages\sakura-core\src packages\sakura-protocol\src packages\sakura-oss\src tests
uv run ty check packages\sakura-core\src packages\sakura-protocol\src packages\sakura-oss\src
```

SakuraIM 仍处在早期阶段。当前重点是把 core、protocol、临时附件缓存和 adapter 规范稳定下来，后续会继续补 adapter 示例、更多协议细节和端到端测试。
