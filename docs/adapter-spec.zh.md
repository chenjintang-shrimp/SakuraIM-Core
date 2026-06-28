# SakuraIM Adapter 协议

本文档描述了适配器必须实现的线路协议，用于连接 Sakura Core 并使用临时附件缓存。

## 传输

适配器通过 WebSocket 连接到 Sakura Core：

```text
ws://<core-host>:21229/adapter/ws
```

所有 WebSocket 载荷都是 JSON 对象。每个载荷都有一个 `type` 字段。

已知的数据包类型：

```text
hello
welcome
message
command
info
ack
```

## 握手

打开 WebSocket 后，适配器必须且只能发送一个 `hello` 数据包。

```json
{
  "type": "hello",
  "aid": "2c186a5f-84d2-4c69-8d8a-f7713d45b89a",
  "platform": "telegram"
}
```

字段：

| 字段         | 类型       | 说明              |
|------------|----------|-----------------|
| `aid`      | UUID 字符串 | 稳定的适配器实例 ID。    |
| `platform` | 字符串      | 用于用户绑定和路由的平台名称。 |

收到有效的 `hello` 后，core 会回复一个 `welcome` 数据包。

```json
{
  "type": "welcome",
  "core": "sakura-core",
  "version": "0.1.0",
  "capabilities": {
    "attachments": {
      "enabled": true,
      "base_url": "http://127.0.0.1:21230",
      "ttl_seconds": 86400,
      "max_size_bytes": 33554432,
      "hash": "sha256",
      "auth": {
        "type": "bearer",
        "token": "..."
      }
    }
  }
}
```

附件 token 的作用域限定在 `aid` 和当前在线会话内。Core 只存储 token 的哈希值。适配器断开连接后，core 会吊销该 token，之后使用该
token 发起的 OSS 请求都会失败。

适配器不得将该 token 持久化为长期凭据。

## 用户命令

适配器以 `command` 数据包发送会影响 SakuraIM 状态的用户操作。

```json
{
  "type": "command",
  "command": "bind",
  "args": [
    "alice"
  ],
  "from_aid": "2c186a5f-84d2-4c69-8d8a-f7713d45b89a",
  "sender_pid": "platform-user-id",
  "seq": 1
}
```

字段：

| 字段           | 类型       | 说明                                                         |
|--------------|----------|------------------------------------------------------------|
| `command`    | 字符串      | `bind`、`verify`、`new`、`delete`、`resume`、`temp_session` 之一。 |
| `args`       | 字符串数组    | 命令参数。                                                      |
| `from_aid`   | UUID 字符串 | 发送该命令的适配器 ID。                                              |
| `sender_pid` | 字符串      | 命令发送者的平台用户 ID。                                             |
| `seq`        | 整数       | 适配器本地的命令序列号。                                               |

已实现的命令：

| 命令       | 参数                     | 含义                    |
|----------|------------------------|-----------------------|
| `bind`   | `[username]`           | 将平台用户绑定到 SakuraIM 用户。 |
| `verify` | `[code]`               | 确认发送给已有用户的绑定请求。       |
| `new`    | `[username, platform]` | 与某个平台上的目标用户创建会话。      |
| `delete` | `[sid]`                | 结束已有会话。               |
| `resume` | `[]` 或 `[sid]`         | 列出会话或恢复指定会话。          |

`temp_session` 存在于协议枚举中，但 core 尚未实现。

Core 会用 `info` 数据包返回命令结果。

```json
{
  "type": "info",
  "to_aid": "2c186a5f-84d2-4c69-8d8a-f7713d45b89a",
  "to_pid": "platform-user-id",
  "info_type": "info",
  "body": {
    "event": "bind_success",
    "username": "alice",
    "uid": 1
  }
}
```

对于错误，`info_type` 为 `error`，并由 `body.error_type` 标识具体错误。

## 消息

适配器以 `message` 数据包发送和接收聊天载荷。

```json
{
  "type": "message",
  "message_type": "normal",
  "sender_aid": "2c186a5f-84d2-4c69-8d8a-f7713d45b89a",
  "sender_pid": "platform-user-id",
  "body": "hello",
  "attachments": [],
  "is_reply": false,
  "reply_seq": 0
}
```

字段：

| 字段             | 类型       | 说明                                   |
|----------------|----------|--------------------------------------|
| `message_type` | 字符串      | `normal`、`attachment`、`reaction` 之一。 |
| `sender_aid`   | UUID 字符串 | 接收到平台消息的适配器 ID。                      |
| `sender_pid`   | 字符串      | 发送者的平台用户 ID。                         |
| `body`         | 字符串      | 文本正文或适配器定义的轻量载荷。                     |
| `attachments`  | 字符串数组    | 已上传到 Sakura OSS 的 SHA-256 对象 ID。     |
| `is_reply`     | 布尔值      | 该消息是否回复了上一条消息。                       |
| `reply_seq`    | 整数       | 被回复消息的序列号；未使用时为 `0`。                 |

每个附件条目都必须是 64 个字符的十六进制 SHA-256 字符串。

Core 不会上传、下载、检查或转换附件字节。它只负责路由消息并保留 `attachments` 数组。

## 附件缓存

如果 `welcome.capabilities.attachments.enabled` 为 true，适配器可以将 Sakura OSS 用作临时对象缓存。

该缓存用于表情、语音片段、贴纸、照片等临时聊天媒体。它不是持久存储。对象可能会在 `ttl_seconds` 后过期。

### 认证

每个 OSS 请求都必须包含在 `welcome` 中收到的 bearer token：

```text
Authorization: Bearer <token>
```

该 token 由 core 验证。适配器与 core 断开连接后，该 token 会被吊销。

### 上传流程

发送带附件的消息前：

1. 对要发送的精确字节计算 SHA-256。
2. 检查对象是否已存在。
3. 如果不存在，则上传对象。
4. 将 SHA-256 字符串放入消息的 `attachments` 数组。

检查是否存在：

```http
HEAD /objects/{sha256}
Authorization: Bearer <token>
```

状态码：

| 状态    | 含义               |
|-------|------------------|
| `200` | 对象存在且未过期。        |
| `404` | 对象不存在或已过期。       |
| `400` | 无效的 SHA-256 路径值。 |
| `401` | token 缺失、无效或已吊销。 |

上传：

```http
PUT /objects/{sha256}
Authorization: Bearer <token>
Content-Type: image/png

<raw bytes>
```

状态码：

| 状态    | 含义                     |
|-------|------------------------|
| `201` | 对象已创建。                 |
| `200` | 对象已存在，且 TTL 已刷新。       |
| `413` | 对象超过 `max_size_bytes`。 |
| `422` | 上传的字节与 `{sha256}` 不匹配。 |
| `401` | token 缺失、无效或已吊销。       |

### 下载流程

收到带附件的消息时，按 SHA-256 下载每个对象：

```http
GET /objects/{sha256}
Authorization: Bearer <token>
```

状态码：

| 状态    | 含义               |
|-------|------------------|
| `200` | 响应体为原始字节。        |
| `404` | 对象不存在或已过期。       |
| `401` | token 缺失、无效或已吊销。 |

成功响应包含：

```text
Content-Type: <stored content type>
Content-Length: <byte length>
ETag: <sha256>
```

适配器应将 `404` 视为“附件不可用”，并渲染适合对应平台的降级展示。

## 适配器职责

适配器负责：

- 为适配器实例保持稳定的 `aid`。
- 将平台用户映射到 `sender_pid`。
- 根据用户操作发送 `bind`、`verify`、`new`、`delete` 和 `resume` 命令。
- 在消息中引用附件前上传附件字节。
- 下载传入消息中引用的附件。
- 优雅地处理已过期附件。
- 断开连接后重新连接到 core，并等待新的 `welcome` token。

适配器不得：

- 在 `message.attachments` 中发送 base64 附件字节。
- 在 WebSocket 断开连接后复用 OSS token。
- 假设 Sakura OSS 总是启用。
- 在 core 实现 `temp_session` 前假设它可用。
