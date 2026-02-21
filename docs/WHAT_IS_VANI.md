# What is Vani? — A Detailed Explainer

_Last updated: 2026-02-21_

---

## The One-Line Version

Vani is an **open-source plumbing layer** that connects a microphone (in any Indian language) to an AI brain and back to a speaker — handling all the India-specific complexity that nobody else standardises.

---

## Table of Contents

1. [The Problem We're Solving](#1-the-problem-were-solving)
2. [A Real Scenario](#2-a-real-scenario)
3. [What Vani Actually Does (Step by Step)](#3-what-vani-actually-does-step-by-step)
4. [The Five Hard Problems](#4-the-five-hard-problems)
5. [Architecture — How the Pieces Fit](#5-architecture--how-the-pieces-fit)
6. [The Protocol — Why It Matters](#6-the-protocol--why-it-matters)
7. [Who Is This For?](#7-who-is-this-for)
8. [What Exists Today Without Vani](#8-what-exists-today-without-vani)
9. [Comparison With Other Approaches](#9-comparison-with-other-approaches)
10. [Summary](#10-summary)

---

## 1. The Problem We're Solving

India has **1.4 billion people**. Only about **12% speak or write fluent English**. Yet almost every AI voice infrastructure today — OpenAI's Realtime API, LiveKit, Pipecat, Retell — is **built English-first**. Indian languages are an afterthought, bolted on via a third-party plugin.

The individual pieces exist:

- **Sarvam AI** has Saaras v3 — a streaming speech-to-text model for Hindi, Tamil, Telugu, Bengali, Marathi (sub-250ms latency)
- **AI4Bharat** has IndicTrans2 — translation across all 22 scheduled Indian languages
- **MeitY's Bhashini** aggregates government-funded models at national scale

**But nobody has connected them into a standard pipeline.** Every developer who builds a Hindi voice bot, a Tamil IVR, or a Telugu customer support agent has to:

1. Figure out what audio format each API expects
2. Handle Sarvam's WebSocket protocol (which differs from Bhashini's REST API, which differs from AI4Bharat's gRPC)
3. Deal with code-switching (people mix Hindi and English mid-sentence — "Hinglish")
4. Support callers on 2G networks in rural India (different codec, different latency expectations)
5. Comply with India's data protection law (DPDP Act — audio can't leave Indian servers)
6. Wire up tool calls so the bot can actually DO things (check PAN status, look up mandi prices)

**They solve all of this from scratch, every single time.**

Vani says: solve it once, in an open protocol, so nobody ever has to solve it again.

---

## 2. A Real Scenario

Imagine a **farmer in rural Bihar** calling an agricultural helpline from a basic phone on a 2G connection. He speaks Bhojpuri-inflected Hindi, mixed with occasional English words like "market price" and "fertiliser."

Here's what needs to happen in the ~3 seconds between him speaking and hearing a response:

```
           Farmer speaks               What needs to happen                        What he hears back
    ┌─────────────────────┐    ┌────────────────────────────────┐    ┌────────────────────────────────┐
    │ "Bhai aaj Azadpur   │    │ 1. Audio codec: AMR-NB 8kHz   │    │ "Azadpur mandi mein aaj wheat │
    │  mandi mein wheat   │───►│    (he's on 2G, can't send    │───►│  ka modal price ₹2350 per     │
    │  ka kya price hai?" │    │     high-quality audio)        │    │  quintal hai. Kal se ₹50      │
    └─────────────────────┘    │ 2. STT: Recognise Bhojpuri    │    │  badha hai."                   │
                               │    Hindi + English code-switch │    └────────────────────────────────┘
                               │ 3. Detect "wheat", "Azadpur   │
                               │    mandi", "price" → tool call│
                               │ 4. Call eNAM API for live price│
                               │ 5. LLM formats response in    │
                               │    the farmer's Hindi register │
                               │ 6. TTS in Hindi, compressed   │
                               │    to AMR-NB for 2G delivery   │
                               │ 7. All data stays in India     │
                               │    (DPDP Act compliance)       │
                               └────────────────────────────────┘
```

**Every numbered step above is a separate hard problem.** Vani handles all seven.

---

## 3. What Vani Actually Does (Step by Step)

Vani defines a **complete pipeline** from microphone to speaker, with a protocol (like HTTP for the web) that any app can speak:

### Step 1: Session Negotiation

Before any audio flows, the client and gateway agree on:

- **Language**: "I'll be speaking Telugu" → `te-IN`
- **Audio codec**: "I'm on 2G" → AMR-NB 8kHz / "I'm on WiFi" → PCM 16kHz
- **Backend preference**: "Use Sarvam for STT, fall back to Bhashini"
- **Capabilities**: "I want code-switch detection" / "I want dialect routing"
- **Data residency**: "Keep all audio in India" (default)

This is like an HTTP content negotiation, but for voice.

### Step 2: Audio Streaming (STT)

The client streams audio chunks to the gateway. The gateway routes them to the configured STT backend (Sarvam, AI4Bharat, or Bhashini). Transcripts stream back in real-time:

```
Client ──AudioChunk──► Gateway ──AudioChunk──► Sarvam STT
Client ◄──"aaj Azad..."──── Gateway ◄──partial transcript────
Client ◄──"aaj Azadpur mandi..."── Gateway ◄──partial────────
Client ◄──"aaj Azadpur mandi mein wheat ka kya price hai?"──── [FINAL]
```

The transcript includes **code-switch annotations**:

```
text: "aaj Azadpur mandi mein wheat ka kya price hai?"
code_switch_spans:
  - [25, 30] → "wheat" → language: en
  - [39, 44] → "price" → language: en
```

### Step 3: LLM Processing

The final transcript goes to an LLM (Sarvam-M, GPT-4, etc.) with:

- Conversation history
- System prompt (in the user's language)
- Available tool definitions

If the LLM decides it needs data, it makes a **tool call**.

### Step 4: Action Execution (MCP Tool Calls)

The LLM says: "I need to call `enam_mandi_price` with `crop=wheat, mandi=Azadpur`."

Vani wraps this as an MCP action, dispatches it, gets the result (`₹2350/quintal`), feeds it back to the LLM, and the LLM generates a natural response.

### Step 5: Text-to-Speech

The LLM's text response goes to a TTS backend (Sarvam Bulbul, Bhashini TTS). Audio chunks stream back to the client.

### Step 6: Turn Management

Throughout all of this, Vani emits **turn signals** so the client UI knows what state the conversation is in:

```
🎙 LISTENING    → "show the red recording dot"
🧠 THINKING     → "show a spinner"
🔊 SPEAKING     → "play the audio, show waveform"
✅ END_OF_TURN  → "ready for next utterance"
💤 IDLE         → "conversation paused"
```

---

## 4. The Five Hard Problems

### Problem 1: Code-Switching ("Hinglish")

This is NOT an edge case in India. It's how **300+ million people talk every day.**

```
Normal speech:    "मुझे ये laptop बहुत पसंद है, but price thoda zyada hai"
                   [Hindi] [English] [Hindi]    [English]  [Hindi+English]
```

Most STT systems either:

- Transcribe everything as Hindi (miss "laptop", "price")
- Transcribe everything as English (garbled Hindi)
- Return gibberish at language boundaries

Vani's protocol **requires** STT backends to detect code-switch boundaries and annotate them as spans with language tags and confidence scores. This means downstream LLMs and TTS engines know exactly which parts are Hindi and which are English.

Defined profiles: Hinglish (hi-en, ~300M speakers), Tanglish (ta-en, ~50M), Tenglish (te-en, ~60M), Banglish (bn-en, ~70M), Marathlish (mr-en, ~40M), and more.

### Problem 2: Network Diversity (2G to 5G)

A developer in Bangalore on 5G and an ASHA health worker in rural Chhattisgarh on 2G **both need the voice agent to work**. But they can't use the same audio format — 16kHz PCM over a 2G connection would be unusable.

Vani defines three **transport tiers** that auto-negotiate:

| Tier  | Network | Codec            | Latency Target | User                      |
| ----- | ------- | ---------------- | -------------- | ------------------------- |
| **A** | 2G/EDGE | AMR-NB 8kHz      | ≤2.5s          | Rural IVR, feature phones |
| **B** | 3G      | Opus 16kHz       | ≤1.5s          | Budget smartphones        |
| **C** | 4G/WiFi | PCM 16kHz/16-bit | ≤0.5s          | Modern devices            |

The gateway adapts everything automatically — STT gets the right format, TTS output gets compressed to match, streaming strategy changes (batch on 2G, real-time on 4G).

### Problem 3: Dialect Variance

"Hindi" isn't one language. A farmer from Bihar speaks Bhojpuri-inflected Hindi with a Word Error Rate **2-3× higher** on standard models compared to Delhi Hindi. Same for Madurai Tamil vs. Chennai Tamil, or Telangana Telugu vs. Coastal Telugu.

Vani specifies a **dialect detection and routing** system:

- First utterance is analysed for dialectal markers
- If a dialect-specific STT model is available, audio is re-routed mid-session
- Dialect tag is exposed in the transcript (`hi-IN-Bhojpuri`, `ta-IN-Madurai`, `te-IN-Telangana`)

Defined dialect tags for: 8 Hindi dialects, 5 Tamil dialects, 4 Telugu dialects, 4 Bengali dialects, 4 Marathi dialects.

### Problem 4: Backend Fragmentation

Three major Indian language AI providers exist. None of them have the same API:

|               | Sarvam AI                       | AI4Bharat                   | Bhashini                   |
| ------------- | ------------------------------- | --------------------------- | -------------------------- |
| **STT**       | WebSocket, base64 WAV JSON      | gRPC, batch                 | REST, batch                |
| **TTS**       | REST, JSON                      | HuggingFace, local          | REST, ULCA                 |
| **Auth**      | `Api-Subscription-Key` header   | None (self-hosted)          | `ulcaApiKey` in body       |
| **Format**    | Custom JSON envelope            | Standard protobuf           | ULCA envelope              |
| **Strengths** | Low-latency streaming, 11 langs | Open weights, self-hostable | 22 languages, free (MeitY) |

Today, if you build on Sarvam and want to add Bhashini as a fallback, you rewrite everything. Vani provides a **unified backend interface** — swap `SarvamSTTBackend` for `BhashiniSTTBackend` with one line of code. Same `transcribe_stream()`, same `TranscriptResult`, same code-switch spans.

### Problem 5: Data Sovereignty (DPDP Act)

India's Digital Personal Data Protection Act (2023) has strict requirements about where personal data (including voice recordings) can be processed. Vani defaults to `DATA_RESIDENCY_INDIA_ONLY`:

- Sarvam and Bhashini servers are in India
- Audio data never leaves Indian data centres by default
- PII fields (`aadhaar_number`, `pan_number`) are never logged at the gateway
- Applications must explicitly opt out if they want to use non-Indian infrastructure

---

## 5. Architecture — How the Pieces Fit

```
┌──────────────────────────────────────────────────────────────────────┐
│                          YOUR APPLICATION                            │
│  (IVR system / mobile app / web chatbot / kiosk / Twilio bridge)    │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ VAM/1.0 Protocol (gRPC / WebSocket)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        VANI GATEWAY                                  │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Session Mgr    │  │ Turn State     │  │ Action Dispatcher      │ │
│  │ (codec, lang,  │  │ Machine        │  │ (MCP tool calls)       │ │
│  │  backend pick) │  │ (LISTEN→THINK  │  │                        │ │
│  │                │  │  →SPEAK→IDLE)  │  │ enam_mandi_price       │ │
│  └────────────────┘  └────────────────┘  │ pan_validate           │ │
│                                           │ aadhaar_verify_otp     │ │
│  ┌─────────────────────────────────────┐  │ pm_kisan_eligibility   │ │
│  │      Pluggable Backend Layer        │  └────────────────────────┘ │
│  │                                     │                             │
│  │  ┌───────────┐ ┌─────────────────┐  │                             │
│  │  │    STT    │ │      LLM        │  │                             │
│  │  │ Sarvam    │ │  Sarvam-M /     │  │                             │
│  │  │ AI4Bharat │ │  GPT-4 /        │  │                             │
│  │  │ Bhashini  │ │  Airavata       │  │                             │
│  │  └───────────┘ └─────────────────┘  │                             │
│  │  ┌───────────┐ ┌─────────────────┐  │                             │
│  │  │    TTS    │ │      NMT        │  │                             │
│  │  │ Bulbul v3 │ │  IndicTrans2    │  │                             │
│  │  │ AI4BTTS   │ │  Mayura v1      │  │                             │
│  │  │ Bhashini  │ │  Bhashini ULCA  │  │                             │
│  │  └───────────┘ └─────────────────┘  │                             │
│  └─────────────────────────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
```

The gateway is the orchestrator. It:

1. **Negotiates** session parameters with the client
2. **Routes** audio to the right STT backend
3. **Manages** the conversation turn state machine
4. **Dispatches** tool calls when the LLM needs real data
5. **Streams** TTS audio back to the client
6. **Enforces** data residency, codec constraints, and failover policies

---

## 6. The Protocol — Why It Matters

Vani is defined as a **Protobuf + gRPC protocol** (like HTTP is for the web). Three `.proto` files define everything:

| File            | What It Defines                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------------------ |
| `session.proto` | Session negotiation — language, codec, backends, capabilities, data residency                          |
| `stream.proto`  | Bidirectional streaming — audio chunks, transcripts (with code-switch spans), turn signals, TTS chunks |
| `action.proto`  | Tool execution — MCP tool call/result envelopes that travel over the same stream                       |

### Why a protocol and not just a library?

A library locks you into Python (or whatever language). A protocol means:

- **Any language can implement it** — Python, Go, Rust, JavaScript, Java
- **Any company can be conformant** — Sarvam could natively speak VAM/1.0, so could Bhashini
- **Interoperability** — a Tamil IVR built by Company A can swap backends to Company B without rewriting
- **Conformance testing** — the YAML test suite (32 tests) validates implementations against the spec
- **Ecosystem growth** — others can build gateways, bridges, adapters on top of the same protocol

This is the same pattern that made HTTP, gRPC, and WebRTC successful.

---

## 7. Who Is This For?

### Developers building Indian voice agents

Instead of wiring up Sarvam WebSockets, handling auth headers, parsing response envelopes, managing turn state, and implementing silence detection yourself — you write:

```python
gateway = VaniGatewayStub(
    config=SessionConfig.for_language("te-IN"),
    stt=SarvamSTTBackend(api_key="..."),
    llm=SarvamLLMBackend(api_key="..."),
    tts=SarvamTTSBackend(api_key="..."),
)

async for event in gateway.process_audio(mic_stream()):
    if event.transcript:
        print(event.transcript.text)
```

### Companies with Indian customer bases

Banks, insurance companies, e-commerce, government services — anyone running call centres or IVR systems for Indian customers. Vani gives them backend portability (switch from Sarvam to Bhashini without rewriting) and compliance by default.

### AI4Bharat / Sarvam / Bhashini themselves

A standard protocol increases their TAM (total addressable market). If developers build on Vani, those developers can easily USE their backends. It's the rising tide.

### Government digital infrastructure projects

Bhashini, Digital India, PM-KISAN, NFSA — all need vernacular voice interfaces. A conformance-tested protocol with data residency defaults is exactly what government RFPs look for.

---

## 8. What Exists Today Without Vani

| Approach                         | Problem                                                                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Build directly on Sarvam API** | Locked in. No fallback. Must handle their WS protocol, auth quirks, codec requirements yourself.                                                       |
| **Build on OpenAI Realtime API** | English-first. Indian languages are second-class. No code-switching. Data leaves India. No 2G support.                                                 |
| **Build on LiveKit / Pipecat**   | Great frameworks, but no Indian language-specific features. No codec negotiation for 2G. No dialect routing. No Bhashini/AI4Bharat integration.        |
| **Build from scratch**           | Every company reinvents the same wheels — code-switching, codec negotiation, backend failover, turn management. 3-6 months of engineering per company. |

Vani is the layer between your app and these backends that handles all the India-specific complexity.

---

## 9. Comparison With Other Approaches

```
                        ┌──────────────────────────────────────┐
                        │        What each thing is            │
                        ├──────────────────────────────────────┤
 OpenAI Realtime API    │ English-first hosted voice pipeline  │
 LiveKit Agents         │ WebRTC infra + agent framework       │
 Pipecat               │ Python voice pipeline framework      │
 Bhashini              │ Govt-funded Indian NLP model hub     │
 Sarvam AI             │ Indian language AI API provider      │
                        │                                      │
 VANI                   │ The PROTOCOL that connects all of    │
                        │ the above for Indian languages,      │
                        │ with code-switching, dialect routing, │
                        │ 2G codec support, MCP actions, and   │
                        │ data residency built in.             │
                        └──────────────────────────────────────┘
```

Vani doesn't replace any of those — it's the **glue layer** that makes them work together for India.

---

## 10. Summary

| Question                  | Answer                                                                                                                      |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **What is it?**           | An open-source protocol + Python SDK for Indian language voice agents                                                       |
| **What does it solve?**   | The 5 hard problems: code-switching, 2G-to-5G transport, dialect variance, backend fragmentation, data sovereignty          |
| **What does it produce?** | A standard Voice↔Text↔Action pipeline that works across Sarvam, AI4Bharat, and Bhashini                                     |
| **Who needs it?**         | Anyone building voice AI for Indian users — developers, enterprises, government projects                                    |
| **Why a protocol?**       | Interoperability, language-agnostic, conformance-testable, ecosystem-enabling                                               |
| **What's the status?**    | v0.1.0-alpha — working end-to-end with Sarvam STT, LLM, and TTS. 99 tests passing. Live CLI demo tested with Telugu speech. |

---

_वाणी — Sanskrit for speech, voice, the goddess of language._
_Built for Bharat._
