# VAM/1.0 — Transport & Bandwidth Profile Specification

**Revision:** 1.0-draft · **Date:** 2026-02-18

---

## 1. Design Philosophy

India's network landscape is stratified more sharply than any other major economy:
a 5G-connected developer in Bengaluru and a 2G-limited ASHA worker in rural
Chhattisgarh both need Vani to work. The transport specification defines three
tiers that adapt the audio codec, streaming strategy, and TTS delivery mechanism
to the available bandwidth, negotiated as part of `SessionInitRequest.audio_profile`.

---

## 2. Transport Architecture

```
User Device                 Edge / Cloud
    │                            │
    │  Tier A: AMR-NB 8kHz       │
    │──WebRTC or WebSocket──────►│
    │  (2G/EDGE, <400 Kbps)      │
    │                            │
    │  Tier B: Opus 16kHz        │
    │──WebSocket or WebRTC──────►│
    │  (3G, ~1–5 Mbps)           │
    │                            │
    │  Tier C: PCM 16kHz/16-bit  │
    │──gRPC bidirectional stream►│
    │  (4G+ / LAN / >10 Mbps)    │
                                 │
                    ┌────────────┴──────────────────┐
                    │  Vani Gateway (gRPC internal)  │
                    │  ──►STT Backend (gRPC stream) │
                    │  ──►LLM Backend (HTTP/2)       │
                    │  ──►TTS Backend (gRPC stream)  │
                    │  ──►Action Servers (HTTP/MCP)  │
                    └───────────────────────────────┘
```

---

## 3. Bandwidth Tiers

### Tier A — 2G / EDGE (< 400 Kbps available)

**Target:** Rural kiosk, ASHA workers, Kisan Call Center callers, IVR on 2G SIM.

| Parameter          | Value                                          |
| ------------------ | ---------------------------------------------- |
| Audio codec        | AMR-NB, 8 kHz, 12.2 kbps (narrow-band)         |
| Chunk size         | 160 bytes = 20ms frame (AMR standard frame)    |
| Transport          | WebSocket `text/binary` frames OR SIP/RTP      |
| STT mode           | **Batch with VAD gating**: client buffers 1–3s |
|                    | of voiced audio, sends complete utterance      |
| TTS delivery       | Pre-synthesized at full quality; sent as a     |
|                    | single binary payload after LLM completes      |
| End-to-end latency | Target: ≤ 2.5 seconds (relaxed for low BW)     |
| Barge-in           | Disabled (round-trip cost too high)            |

**AudioProfile in SessionInitRequest:**

```protobuf
AudioProfile {
  codec: AUDIO_CODEC_AMR_NB_8K,
  sample_rate: 8000,
  channels: 1,
  bitrate_kbps: 12
}
```

**Gateway behavior on Tier A:**

- MUST NOT attempt streaming STT; buffer full utterance before dispatch
- MUST compress TTS output to AMR-NB or narrow-band Opus before sending
- MAY pre-fetch common response phrases to reduce TTS round-trip
- SHOULD limit LLM context window to reduce first-token latency

---

### Tier B — 3G / HSPA (1–5 Mbps)

**Target:** Small-town merchants, rural 3G coverage, WhatsApp voice calls.

| Parameter          | Value                                            |
| ------------------ | ------------------------------------------------ |
| Audio codec        | Opus, 16 kHz, 32 kbps (wide-band)                |
| Chunk size         | 320–640 bytes = 20–40ms Opus frames              |
| Transport          | WebSocket (browser/mobile) or gRPC (server)      |
| STT mode           | **Streaming**: VAD detects end-of-speech after   |
|                    | 400ms trailing silence; dispatch to STT          |
| TTS delivery       | **Streaming**: first TTS chunk sent as soon as   |
|                    | first sentence is synthesized                    |
| End-to-end latency | Target: ≤ 700ms for simple responses             |
| Barge-in           | Enabled (client sends `VAD_SIGNAL_VOICED` during |
|                    | TTS to signal interrupt)                         |

**AudioProfile:**

```protobuf
AudioProfile {
  codec: AUDIO_CODEC_OPUS_16K,
  sample_rate: 16000,
  channels: 1,
  bitrate_kbps: 32
}
```

---

### Tier C — 4G+ / LAN / WiFi (> 10 Mbps)

**Target:** Urban mobile users, web browsers, call center agents, server-to-server.

| Parameter          | Value                                           |
| ------------------ | ----------------------------------------------- |
| Audio codec        | PCM signed 16-bit, 16 kHz, mono                 |
| Chunk size         | 320–960 bytes = 10–60ms PCM frames              |
| Transport          | **gRPC bidirectional streaming** (primary)      |
|                    | WebRTC (for browser/mobile last-mile)           |
| STT mode           | **Full duplex streaming**: partial transcripts  |
|                    | emitted every 200–400ms during speech           |
| TTS delivery       | **Chunk-pipelined**: TTS starts while LLM is    |
|                    | still generating; sentence-by-sentence          |
| End-to-end latency | Target: ≤ 300ms (Sarvam Samvaad benchmark tier) |
| Barge-in           | Enabled; gateway detects VAD in-flight and      |
|                    | cancels pending TTS synthesis                   |

**AudioProfile:**

```protobuf
AudioProfile {
  codec: AUDIO_CODEC_PCM_16K_16,
  sample_rate: 16000,
  channels: 1,
  bitrate_kbps: 256   // PCM: sample_rate * bit_depth / 1000 = 16000*16/1000 = 256
}
```

---

## 4. Codec Negotiation Algorithm

The session codec is negotiated in `SessionInitRequest` / `SessionInitResponse`:

```
Client sends: AudioProfile { codec: AUDIO_CODEC_PCM_16K_16 }
Gateway responds:
  IF gateway supports PCM_16K_16:
    negotiated_audio_profile = PCM_16K_16  (unchanged)
  ELSE IF gateway supports OPUS_16K:
    negotiated_audio_profile = OPUS_16K    (downgrade to Tier B)
    degraded_capabilities += ["audio_codec_downgraded_to_opus"]
  ELSE:
    negotiated_audio_profile = AMR_NB_8K   (minimum viable)
    degraded_capabilities += ["audio_codec_downgraded_to_amr"]
```

The client MUST use the `negotiated_audio_profile` codec for all subsequent
`AudioChunk` messages. Sending audio in a non-negotiated codec MUST trigger
`StreamError { code: AUDIO_CORRUPT }`.

---

## 5. WebRTC for Browser / Mobile Last-Mile

For browser and mobile clients, the recommended last-mile transport is **WebRTC**
with a Vani WebRTC-to-gRPC bridge at the edge. This provides:

- NAT traversal (STUN/TURN) for mobile clients behind carrier NAT
- Opus codec with Chromium's built-in encoder (Tier B by default)
- Adaptive bitrate control (reduces codec when network degrades)
- DTLS-SRTP encryption (audio encrypted before leaving the device)

The WebRTC bridge converts incoming WebRTC audio tracks into `AudioChunk`
gRPC messages and forwards them to the Vani Gateway.

**WebRTC-to-gRPC bridge behavior:**

- MUST honor codec negotiated in Vani session (translate WebRTC offer/answer)
- MUST NOT buffer more than 200ms of audio before forwarding
- SHOULD use a TURN server co-located in the same Indian cloud region as
  the Vani Gateway (Mumbai, Hyderabad) to minimize RTT

---

## 6. SIP / PSTN Integration (Telephony)

For traditional telephony (Exotel IVR, Plivo, Twilio India):

- Incoming SIP calls arrive as G.711 μ-law or A-law 8kHz
- A SIP serializer (see Pipecat Exotel/Plivo compatibility notes) converts
  to `AUDIO_CODEC_PCM_8K_16` or `AUDIO_CODEC_AMR_NB_8K` before feeding to
  the Vani Gateway
- The Vani session MUST be pre-provisioned (no interactive SDP negotiation
  during a live call); language hints are passed from IVR metadata or
  caller ANI prefix (e.g., +91-44-XXXX → `ta-IN` hint for Chennai number)

---

## 7. Edge Deployment

For rural or on-premises deployments (`DATA_RESIDENCY_ON_PREM`):

- Tier A is the required baseline; Tier B is strongly recommended
- Model backends run on local hardware: quantized IndicWhisper (4-bit GGUF),
  small TTS model, and a ≤7B parameter LLM
- The edge node syncs only model weights and configuration — no audio data
  leaves the premise
- Edge nodes MUST implement `VaniSessionService` and `VaniStreamService`
  with at minimum the `CUSTOM` backend pointing to locally-hosted models

Minimum recommended hardware for an edge node:

- NVIDIA Jetson Orin NX (16GB) or equivalent
- 32 GB eMMC storage
- 100 Mbps LAN to local clients
- Offline-capable (no mandatory internet for session processing)
