# SakuraIM Adapter Protocol

This document describes the wire protocol an adapter must implement to connect
to Sakura Core and use the temporary attachment cache.

## Transport

Adapters connect to Sakura Core over WebSocket:

```text
ws://<core-host>:21229/adapter/ws
```

All WebSocket payloads are JSON objects. Every payload has a `type` field.

Known packet types:

```text
hello
welcome
message
command
info
ack
```

## Handshake

After opening the WebSocket, the adapter must send exactly one `hello` packet.

```json
{
  "type": "hello",
  "aid": "2c186a5f-84d2-4c69-8d8a-f7713d45b89a",
  "platform": "telegram"
}
```

Fields:

| Field      | Type        | Description                                      |
|------------|-------------|--------------------------------------------------|
| `aid`      | UUID string | Stable adapter instance id.                      |
| `platform` | string      | Platform name used for user binding and routing. |

After a valid `hello`, core replies with one `welcome` packet.

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

The attachment token is scoped to the `aid` and current online session. Core
stores only a hash of the token. When the adapter disconnects, core revokes the
token and future OSS requests using that token fail.

Adapters must not persist the token as a long-term credential.

## User Commands

Adapters send user actions that affect SakuraIM state as `command` packets.

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

Fields:

| Field        | Type         | Description                                                         |
|--------------|--------------|---------------------------------------------------------------------|
| `command`    | string       | One of `bind`, `verify`, `new`, `delete`, `resume`, `temp_session`. |
| `args`       | string array | Command arguments.                                                  |
| `from_aid`   | UUID string  | Adapter id sending the command.                                     |
| `sender_pid` | string       | Platform user id of the command sender.                             |
| `seq`        | integer      | Adapter-local command sequence number.                              |

Implemented commands:

| Command  | Args                   | Meaning                                            |
|----------|------------------------|----------------------------------------------------|
| `bind`   | `[username]`           | Bind the platform user to a SakuraIM user.         |
| `verify` | `[code]`               | Confirm a bind request sent to an existing user.   |
| `new`    | `[username, platform]` | Create a session with a target user on a platform. |
| `delete` | `[sid]`                | End an existing session.                           |
| `resume` | `[]` or `[sid]`        | List sessions or resume a specific session.        |

`temp_session` exists in the protocol enum but is not implemented by core yet.

Core responds to command results with `info` packets.

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

For errors, `info_type` is `error` and `body.error_type` identifies the error.

## Messages

Adapters send and receive chat payloads as `message` packets.

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

Fields:

| Field          | Type         | Description                                         |
|----------------|--------------|-----------------------------------------------------|
| `message_type` | string       | One of `normal`, `attachment`, `reaction`.          |
| `sender_aid`   | UUID string  | Adapter id that received the platform message.      |
| `sender_pid`   | string       | Platform user id of the sender.                     |
| `body`         | string       | Text body or adapter-defined lightweight payload.   |
| `attachments`  | string array | SHA-256 object ids already uploaded to Sakura OSS.  |
| `is_reply`     | boolean      | Whether this message replies to a previous message. |
| `reply_seq`    | integer      | Replied message sequence number, or `0` if unused.  |

Every attachment entry must be a 64-character hexadecimal SHA-256 string.

Core does not upload, download, inspect, or transform attachment bytes. It only
routes the message and preserves the `attachments` array.

## Attachment Cache

If `welcome.capabilities.attachments.enabled` is true, adapters may use Sakura
OSS as a temporary object cache.

The cache is for transient chat media such as emoji, voice clips, stickers, and
photos. It is not durable storage. Objects may expire after
`ttl_seconds`.

### Authentication

Every OSS request must include the bearer token received in `welcome`:

```text
Authorization: Bearer <token>
```

The token is validated by core. After the adapter disconnects from core, the
token is revoked.

### Upload Flow

Before sending a message with attachments:

1. Compute SHA-256 over the exact bytes to send.
2. Check whether the object already exists.
3. Upload it if missing.
4. Put the SHA-256 string in the message `attachments` array.

Check existence:

```http
HEAD /objects/{sha256}
Authorization: Bearer <token>
```

Status codes:

| Status | Meaning                             |
|--------|-------------------------------------|
| `200`  | Object exists and is not expired.   |
| `404`  | Object is missing or expired.       |
| `400`  | Invalid SHA-256 path value.         |
| `401`  | Missing, invalid, or revoked token. |

Upload:

```http
PUT /objects/{sha256}
Authorization: Bearer <token>
Content-Type: image/png

<raw bytes>
```

Status codes:

| Status | Meaning                                       |
|--------|-----------------------------------------------|
| `201`  | Object created.                               |
| `200`  | Object already existed and TTL was refreshed. |
| `413`  | Object exceeds `max_size_bytes`.              |
| `422`  | Uploaded bytes do not match `{sha256}`.       |
| `401`  | Missing, invalid, or revoked token.           |

### Download Flow

When receiving a message with attachments, download each object by SHA-256:

```http
GET /objects/{sha256}
Authorization: Bearer <token>
```

Status codes:

| Status | Meaning                              |
|--------|--------------------------------------|
| `200`  | Response body is the original bytes. |
| `404`  | Object is missing or expired.        |
| `401`  | Missing, invalid, or revoked token.  |

Successful responses include:

```text
Content-Type: <stored content type>
Content-Length: <byte length>
ETag: <sha256>
```

Adapters should treat `404` as "attachment unavailable" and render a platform
appropriate fallback.

## Adapter Responsibilities

Adapters are responsible for:

- Keeping a stable `aid` for the adapter instance.
- Mapping platform users to `sender_pid`.
- Sending `bind`, `verify`, `new`, `delete`, and `resume` commands from user
  actions.
- Uploading attachment bytes before referencing them in messages.
- Downloading attachments referenced in incoming messages.
- Handling expired attachments gracefully.
- Reconnecting to core and waiting for a fresh `welcome` token after disconnects.

Adapters must not:

- Send base64 attachment bytes in `message.attachments`.
- Reuse an OSS token after WebSocket disconnect.
- Assume Sakura OSS is always enabled.
- Assume `temp_session` works until core implements it.
