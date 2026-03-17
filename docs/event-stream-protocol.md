# Event Stream Protocol (v2)

This document is the canonical protocol reference for `/chat/stream` and `/chat/permit`.

OClaw stream events are v2-only. The server emits `schema_version: "2.0"` envelopes and the CLI consumes only that schema.

## Canonical event envelope

Every SSE `data:` frame from `POST /chat/stream` is a JSON object with this shape:

```json
{
  "schema_version": "2.0",
  "event_id": "<uuid>",
  "sequence": 1,
  "timestamp": "2026-03-17T12:34:56.789Z",
  "event_type": "agent_start",
  "request_id": "<uuid>",
  "session_id": "<session-id>",
  "turn_id": "<uuid-or-null>",
  "payload": {}
}
```

Field semantics:

- `schema_version`: always `"2.0"`
- `event_id`: unique event identifier
- `sequence`: monotonic integer within one stream
- `timestamp`: UTC RFC3339 timestamp with millisecond precision
- `event_type`: one of the allowed event types listed below
- `request_id`: identifier for one `/chat/stream` request; reused for permit decisions
- `session_id`: target chat session
- `turn_id`: current turn id, or `null` for stream-level events
- `payload`: event-specific body

## Allowed `event_type` set

The v2 stream supports only these event types:

- `agent_start`
- `turn_start`
- `message_start`
- `message_update`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `turn_end`
- `agent_end`
- `error`
- `stream_end`

No legacy event names are supported.

## Payload expectations by event type

### `agent_start`

```json
{ "status": "started", "max_iterations": 5 }
```

### `turn_start`

```json
{ "iteration": 1 }
```

### `message_start`

```json
{ "message_id": "<uuid>", "role": "assistant" }
```

### `message_update`

This event is multiplexed by payload shape:

- Content delta:

```json
{ "message_id": "<uuid>", "channel": "content", "delta": "text chunk" }
```

- Thinking delta:

```json
{ "message_id": "<uuid>", "channel": "thinking", "delta": "reasoning chunk" }
```

- Tool call announcement:

```json
{
  "message_id": "<uuid>",
  "tool_call": {
    "name": "read_file",
    "id": "call_123",
    "args": { "filePath": "/tmp/a.txt" }
  }
}
```

- Metrics update:

```json
{ "message_id": "<uuid>", "metrics": { "...": "..." } }
```

### `message_end`

```json
{
  "message_id": "<uuid>",
  "status": "completed",
  "content": "final assistant text",
  "thinking": "final thinking text",
  "tool_call_count": 1
}
```

`status` can be `completed` or `failed`.

### `tool_execution_start`

```json
{
  "tool_name": "read_file",
  "tool_call_id": "call_123",
  "args": { "filePath": "/tmp/a.txt" }
}
```

### `tool_execution_update`

Approval lifecycle event:

```json
{
  "tool_name": "read_file",
  "tool_call_id": "call_123",
  "phase": "approval_requested",
  "args": { "filePath": "/tmp/a.txt" }
}
```

`phase` values:

- `approval_requested`
- `approval_granted`
- `approval_denied`

### `tool_execution_end`

```json
{
  "tool_name": "read_file",
  "tool_call_id": "call_123",
  "status": "succeeded",
  "result": "..."
}
```

`status` values:

- `succeeded` (includes `result`)
- `failed` (includes `error`)
- `denied` (includes denial `result` message)

### `turn_end`

```json
{ "iteration": 1, "status": "succeeded" }
```

`status` can be `succeeded`, `failed`, or `denied`.

### `agent_end`

```json
{ "status": "succeeded" }
```

`status` can be `succeeded` or `failed`.

### `error`

```json
{ "message": "Tool execution failed", "fatal": true }
```

Current implementation emits fatal errors for terminal failures.

### `stream_end`

```json
{ "status": "succeeded" }
```

`status` can be `succeeded` or `failed`.

## Ordering and lifecycle guarantees

- Events are emitted in ascending `sequence` order.
- `agent_start` is the first lifecycle event for each stream.
- For each turn, `turn_start` occurs before any message/tool events for that turn.
- `message_start` precedes related `message_update` events and is followed by `message_end`.
- Tool events for a turn occur after that turn's assistant `message_end`.
- Terminal order is `agent_end` then `stream_end`.
- `stream_end` is the canonical end-of-stream marker.

## `/chat/stream` and `/chat/permit` handshake

1. Client calls `POST /chat/stream` with `{ "message": "...", "session_id": "..." }`.
2. Server responds as SSE; each event includes top-level `request_id`.
3. When a tool needs approval, stream emits `tool_execution_update` with `phase: "approval_requested"`.
4. Client calls `POST /chat/permit` with:

   ```json
   { "request_id": "<request_id-from-stream>", "approved": true }
   ```

5. Stream continues with `approval_granted` or `approval_denied`, then `tool_execution_end`.

Important: `request_id` for `/chat/permit` is the envelope `request_id`, not a nested payload field.

## Legacy compatibility

Legacy event names are not part of the v2 protocol and should not be used by clients.
