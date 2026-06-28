# SakuraIM

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-core-green)](https://fastapi.tiangolo.com/)
[![uv](https://img.shields.io/badge/workspace-uv-purple)](https://docs.astral.sh/uv/)

[English](README.en.md)

SakuraIM 是一个面向多平台 adapter 的消息中继核心。它不试图成为新的聊天客户端，也不替任何平台保存完整的聊天历史；它更像一个轻量的路由层，把不同平台上的用户绑定到统一的
SakuraIM 用户身份，再把会话里的消息转发到合适的 adapter。

项目目前由三个 workspace package 组成。`sakura-protocol` 定义 adapter 和 core 之间共享的 Pydantic 消息模型，`sakura-core`
负责 WebSocket 接入、用户绑定、会话管理和消息路由，`sakura-oss` 则提供一个临时附件缓存服务，用来中转 emoji、语音、贴纸、照片这类聊天媒体。

本仓库使用 Python 3.12 和 uv workspace。安装依赖后可以分别启动 core 和 OSS 服务：

```powershell
uv sync
uv run uvicorn sakura_core.main:app --host 0.0.0.0 --port 21229
uv run uvicorn sakura_oss.main:app --host 0.0.0.0 --port 21230
```

core 默认使用 `sqlite+aiosqlite:///./data/app.db`，OSS 默认使用 `sqlite+aiosqlite:///./data/oss.db`，对象文件默认写入
`./data/objects`。这些值可以通过 `.env` 覆盖。core 侧配置使用 `OSS_BASE_URL`、`OSS_TTL_SECONDS`、`OSS_MAX_SIZE_BYTES`
等变量；OSS 服务自身配置使用 `OSS_DATABASE_URL`、`OSS_OBJECT_ROOT`、`OSS_CORE_VERIFY_URL` 等变量，避免和 core 的数据库配置混用。

adapter
实现者可以从 [Adapters Spec](https://github.com/chenjintang-shrimp/SakuraIM-Core/wiki/SakuraIM-Adapters-SPEC-(Chinese))
开始。那份文档描述了 WebSocket 包格式、`hello`/`welcome`
握手、命令、消息、附件上传下载流程和 token 生命周期。

开发时可以运行测试和静态检查：

```powershell
uv run pytest -q
uv run ruff check packages\sakura-core\src packages\sakura-protocol\src packages\sakura-oss\src tests
uv run ty check packages\sakura-core\src packages\sakura-protocol\src packages\sakura-oss\src
```

SakuraIM
仍处在早期阶段。API和标准变动可能会比较大。请前往我们的 [wiki](https://github.com/chenjintang-shrimp/SakuraIM-Core/wiki/SakuraIM-Adapters-SPEC-(Chinese))
查看最新文档