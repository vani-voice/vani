# VAM/1.0 — Protocol Overview

**Vani: Vernacular Agent Middleware**
**Revision:** 1.0-draft · **Date:** 2026-02-18 · **License:** Apache 2.0

---

## 1. Problem Statement

India has ~1.4 billion people. Fewer than 12% are fluent English speakers. Yet
nearly every production-grade AI voice agent today is built on English-first
infrastructure — OpenAI Realtime API, LiveKit, Pipecat — that treats Indian
languages as an afterthought bolted on via a third-party STT plugin.

The components exist: Sarvam AI's Saaras v3 achieves sub-250ms streaming ASR
for Hindi, Tamil, Telugu, Bengali, and Marathi; AI4Bharat's IndicTrans2 covers
all 22 scheduled languages; MeitY's Bhashini aggregates model quality at national
scale. But no open protocol connects them into a coherent agent stack that
handles the messy realities of Indian conversational speech:

- **Code-switching** mid-sentence ("मुझे ये laptop बहुत पसंद है")
- **Script diversity** across 12+ writing systems
- **Bandwidth variance** from 4G Mumbai to 2G rural Rajasthan
- **Data sovereignty** requirements under India's DPDP Act 2023
- **Dialectal variation** (Bhojpuri Hindi vs. Delhi Hindi vs. Marathi-influenced Hindi)

Vani (Sanskrit: _वाणी_, meaning "speech" or "voice") is an open-source protocol
specification and reference implementation that solves this at the infrastructure
layer so application developers never have to solve it again.

---

## 2. What Vani Is (and Is Not)

**Vani IS:**

- A Protobuf-first, gRPC-based protocol specification for the `Voice↔Text↔Action`
  loop in Indian languages
- A session negotiation standard (language selection, codec negotiation, model
  backend selection, data residency assertion)
- A streaming message schema for audio, transcripts (with code-switch annotations),
  turn signals, and TTS output
- An action execution envelope that wraps MCP tool calls over the same gRPC stream
- An open-source Apache 2.0 project maintainable by the community

**Vani IS NOT:**

- A model: it does not provide STT, TTS, or LLM models — it defines how those
  models are connected
- A hosted service: it is a protocol and reference SDK
- A replacement for Sarvam Samvaad, Bhashini, or AI4Bharat — it is a standard
  those services can implement
- English-only: English support is incidental; Indian languages are the primary target

---

## 3. The Four Actors

```
┌─────────────────────────────────────────────────────────┐
│                         Vani Session                     │
│                                                          │
│  ┌──────────┐   session.proto    ┌───────────────────┐  │
│  │          │ ◄─────────────────► │                   │  │
│  │  Client  │   stream.proto     │   Vani Gateway    │  │
│  │ (mobile/ │ ◄═════════════════► │  (orchestrator)   │  │
│  │  browser/│   action.proto     │                   │  │
│  │  IVR)    │                    └────────┬──────────┘  │
│  └──────────┘                            │              │
│                               ┌──────────┴──────────┐   │
│                               │  Model Backends      │   │
│                               │  ┌────────────────┐  │   │
│                               │  │ STT (Sarvam /  │  │   │
│                               │  │  AI4Bharat /   │  │   │
│                               │  │  Bhashini)     │  │   │
│                               │  ├────────────────┤  │   │
│                               │  │ LLM (Sarvam-M /│  │   │
│                               │  │  Airavata /    │  │   │
│                               │  │  Krutrim)      │  │   │
│                               │  ├────────────────┤  │   │
│                               │  │ TTS (Bulbul /  │  │   │
│                               │  │  AI4BTTS)      │  │   │
│                               │  └────────────────┘  │   │
│                               └──────────┬──────────┘   │
│                                          │               │
│                               ┌──────────┴──────────┐   │
│                               │  Action Servers      │   │
│                               │  (MCP tools:         │   │
│                               │   pan_validate,      │   │
│                               │   enam_mandi_price,  │   │
│                               │   bhashini_translate)│   │
│                               └─────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 3.1 Client

Any caller that speaks the Vani wire protocol. Can be:

- A mobile app (Android/iOS) capturing microphone audio
- A web browser via WebRTC-to-gRPC bridge
- A telephony adapter (Exotel/Plivo SIP → Vani bridge)
- An edge device (Raspberry Pi at a kiosk or gram panchayat office)
- Another agent (agent-to-agent delegation)

### 3.2 Vani Gateway

The central orchestrator. Responsibilities:

- Session negotiation (language detection, codec selection, backend routing)
- VAD (Voice Activity Detection) to detect end-of-speech
- Routing `AudioChunk` stream to the configured STT backend
- Routing transcripts + conversation history to the LLM backend
- Routing LLM output to the TTS backend
- Emitting `TurnSignal` events to drive client UI state
- Dispatching `ActionRequestEnvelope` (MCP tool calls) to Action Servers
- Enforcing data residency constraints

A conformant gateway MUST implement `VaniSessionService` and `VaniStreamService`
as defined in `session.proto` and `stream.proto`.

### 3.3 Model Backends

Pluggable services for each pipeline stage. The gateway selects backends based
on the `ModelPreferences` supplied at session init. Current supported backends:

| Backend     | STT                   | LLM          | TTS               |
| ----------- | --------------------- | ------------ | ----------------- |
| `SARVAM`    | Saaras v3 (WebSocket) | Sarvam-M     | Bulbul v2/v3      |
| `AI4BHARAT` | IndicWhisper (gRPC)   | Airavata     | AI4BTTS           |
| `BHASHINI`  | ULCA ASR pipeline     | —            | ULCA TTS pipeline |
| `AZURE`     | Azure STT (partial)   | Azure OpenAI | Azure TTS         |
| `CUSTOM`    | Any gRPC endpoint     | Any          | Any               |

### 3.4 Action Servers

MCP-compatible servers that expose tools. Registered via `VaniActionService`.
The Vani India Tool Registry (`spec/IndiaToolRegistry.md`) defines canonical
schemas for common Indian use cases.

---

## 4. Session Lifecycle

```
Client                    Gateway
  │                          │
  │ ── InitSession ─────────►│
  │                          │  [negotiate language, codec, backends]
  │ ◄─ SessionInitResponse ──│
  │                          │
  │ ══ AgentStream open ════ │  (bidirectional gRPC stream)
  │                          │
  │ ── AudioChunk ──────────►│ LISTENING
  │ ── AudioChunk ──────────►│
  │ ── AudioChunk (EOS) ────►│
  │                          │
  │ ◄─ TranscriptEvent(P) ───│  LISTENING (partials stream in)
  │ ◄─ TranscriptEvent(P) ───│
  │ ◄─ TranscriptEvent(F) ───│  end of utterance
  │ ◄─ TurnSignal(THINKING) ─│
  │                          │  [LLM generates response]
  │                          │  [tool call if needed ──────────►Action Server]
  │ ◄─ ActionRequest ─────── │  [client executes MCP tool]
  │ ── ActionResult ────────►│
  │                          │  [LLM continues with tool result]
  │ ◄─ TurnSignal(SPEAKING) ─│
  │ ◄─ SynthesisChunk ───────│  TTS streams back
  │ ◄─ SynthesisChunk ───────│
  │ ◄─ SynthesisChunk(final) │
  │ ◄─ TurnSignal(LISTENING) │  ready for next turn
  │                          │
  │ ── EndSession ──────────►│
  │ ◄─ SessionEndNotice ──── │
  │                          │
```

---

## 5. Protocol Versions

The current specification is **VAM/1.0-draft**. The `session_id` in all messages
implicitly carries protocol version context. Future versions will be negotiated
via a `protocol_version` field added in `SessionInitRequest`.

---

## 6. Wire Transport

```
User device ──WebRTC──► Edge Node ──gRPC──► Vani Gateway ──gRPC──► Model Backends
                                            │
                                            └──HTTP/MCP──► Action Servers
```

See `spec/VAM-Transport.md` for full transport tier specifications.

---

## 7. Conformance

An implementation is "VAM/1.0 conformant" if it passes all MUST-level tests in
`conformance/`. SHOULD and MAY tests are aspirational. See `conformance/README.md`.
