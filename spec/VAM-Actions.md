# VAM/1.0 — Action Execution Specification

**Revision:** 1.0-draft · **Date:** 2026-02-18

---

## 1. Design Rationale

The "Action" in Vani's `Voice↔Text↔Action` loop is what transforms a response
system into an **agent** — it can look up real data, write to external systems,
and make decisions grounded in live information.

Vani uses **MCP (Model Context Protocol)** as the semantic action protocol:

- MCP is already natively supported by LiveKit Agents, Claude (Anthropic),
  and OpenAI's agent stack — maximizing ecosystem compatibility
- MCP tool schemas are JSON-based and well-understood by LLMs that have been
  trained on function-calling patterns
- Actions travel over the same gRPC stream as audio and transcripts via
  `ActionRequestEnvelope` / `ActionResultEnvelope` — no second connection

---

## 2. Action Execution Flow

```
Gateway (LLM produces tool call)
    │
    │ 1. LLM response contains tool_use JSON
    │    e.g. { "name": "enam_mandi_price", "input": { "crop": "wheat", "mandi": "Azadpur" } }
    │
    │ 2. Gateway wraps in ActionRequestEnvelope
    │    and emits as GatewayStreamMessage.action_request_payload
    │
    ▼
Client / Action Executor
    │
    │ 3. Client deserializes ActionRequestEnvelope
    │ 4. Client dispatches McpToolCall to the registered Action Server
    │    (HTTP POST to MCP server endpoint, or stdio)
    │ 5. Action Server executes tool, returns McpToolResult
    │
    │ 6. Client wraps result in ActionResultEnvelope
    │    and sends as ClientStreamMessage.action_result_payload
    │
▼ (back to Gateway)
    │
    │ 7. Gateway injects tool result into LLM context
    │ 8. LLM generates final response text
    │ 9. TTS synthesis begins
    │
    ▼
SynthesisChunk emitted → audio plays on client
```

---

## 3. Timing and Latency

### 3.1 Synchronous Actions (default)

The gateway PAUSES TTS synthesis waiting for the action result.

```
LLM generates tool call ──► ActionRequestEnvelope sent ──► [tool executes]
◄── ActionResultEnvelope ── LLM continues ──► TTS starts
```

Timeout: `ActionRequestEnvelope.timeout_ms` (default: 5000ms).
If the result does not arrive within timeout, the gateway MUST:

1. Emit `StreamError { code: STREAM_ERROR_CODE_LLM_BACKEND_ERROR, stage: "action" }`
2. Continue with LLM context that marks the tool as timed out
3. LLM SHOULD gracefully handle the absence of a result in its response

### 3.2 Fire-and-Forget Actions

When `ActionRequestEnvelope.fire_and_forget = true`, the gateway does NOT
pause TTS. Useful for logging, analytics, or post-call CRM updates.

---

## 4. Action Server Registration

Action Servers are registered at session init OR via `VaniActionService.RegisterActionServer`.

**In-session registration (lightweight):** Include server endpoints in
`SessionInitRequest.metadata["action_servers"]` as a JSON array of URIs.
The gateway fetches tool schemas via MCP `list_tools()` during session setup.

**Pre-registered (recommended for production):** Use `VaniActionService.RegisterActionServer`
at application startup. Tools are cached and available immediately.

---

## 5. India Tool Registry Reference

See `spec/IndiaToolRegistry.md` for canonical tool schemas.

A tool with `ToolDeclaration.is_registry_tool = true` MUST conform exactly
to its registry schema — no extra required fields, no schema deviations.
This ensures interoperability: any Vani Action Server implementing
`pan_validate` will work with any Vani Gateway.

---

## 6. Security and Data Sovereignty

- Action Servers with `data_residency = "IN_ONLY"` MUST be hosted within India
- Sessions with `DATA_RESIDENCY_ON_PREM` MUST only use Action Servers
  accessible on the local network (no external tool calls)
- PII fields (Aadhaar numbers, PAN numbers, phone numbers) MUST NOT be
  logged at the gateway layer — only pass-through to the Action Server
- Action Servers handling Aadhaar/PAN MUST be UIDAI/NSDL authorized

---

## 7. Conformance

A gateway with `negotiated_capabilities.action_execution = true` MUST:

- Parse `ClientStreamMessage.action_result_payload` and deserialize as
  `ActionResultEnvelope`
- Match incoming results to pending requests by `call_id`
- Inject `McpToolResult.content[0].text` into the LLM context as a `tool`
  role message following the LLM's function-calling convention
- Emit `ActionRequestEnvelope` within 50ms of the LLM producing a tool call
