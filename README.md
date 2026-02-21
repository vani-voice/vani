# वाणी · Vani

**The WebRTC for Indian AI Agents.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Protocol](https://img.shields.io/badge/protocol-VAM%2F1.0-orange)](spec/VAM-Overview.md)
[![Status](https://img.shields.io/badge/status-alpha-yellow)](CHANGELOG.md)

Vani is an **open-source protocol and middleware library** that handles the messy Voice↔Text↔Action loop for Indian languages. Think of it as the missing link between your LLM and an Indian user calling on a 2G connection — speaking Hinglish.

---

## Why Vani?

India has **1.4 billion people**, only **~12% read or write English fluently**, and 22 official languages. Yet every AI voice agent built for India reinvents the same wheel:

- Phoneme mapping for Hindi retroflex consonants (`ट`, `ठ`, `ड`, `ढ`)
- Code-switching detection ("मुझे एक _laptop_ चाहिए")
- 2G-safe audio codec negotiation (AMR-NB vs. Opus vs. PCM)
- Bhashini / Sarvam / AI4Bharat backend failover
- MeitY DPDP Act data-residency compliance

**Vani solves all of this in one open protocol.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Calling App                          │
│  (your IVR / chatbot / voice UI / telephony bridge)        │
└───────────────────────────┬─────────────────────────────────┘
                            │  VAM/1.0 gRPC stream
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Vani Gateway                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │   ASR    │→ │ LLM/NLU  │→ │   TTS    │  │  Action   │  │
│  │  (STT)   │  │          │  │          │  │   (MCP)   │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│       │              │              │              │        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         Pluggable Backend Layer                     │   │
│  │  Sarvam AI  │  AI4Bharat  │  Bhashini ULCA          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │  MCP tool calls
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              India Tool Registry (MCP servers)              │
│  pan_validate · enam_mandi_price · bhashini_translate       │
│  aadhaar_verify_otp · pm_kisan_eligibility · ...            │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Install

```bash
# Core + Sarvam AI backend
pip install vani[sarvam]

# Core + AI4Bharat (self-hosted, open-weights)
pip install vani[ai4bharat]

# Core + Bhashini ULCA
pip install vani[bhashini]

# Everything
pip install vani[sarvam,ai4bharat,bhashini,dev]
```

### Hello World — Hinglish Support Agent

```python
import asyncio
from vani import SessionConfig
from vani.backends.sarvam import SarvamSTTBackend, SarvamLLMBackend, SarvamTTSBackend
from vani.gateway.stub import VaniGatewayStub

async def main():
    config = SessionConfig.for_hinglish(caller_id="+91-9876543210")

    gateway = VaniGatewayStub(
        config=config,
        stt=SarvamSTTBackend(api_key="sk-..."),
        llm=SarvamLLMBackend(api_key="sk-..."),
        tts=SarvamTTSBackend(api_key="sk-..."),
        system_prompt="आप एक helpful customer support agent हैं।",
    )

    async for event in gateway.process_audio(your_audio_stream()):
        if event.transcript and event.transcript.is_final:
            print("USER:", event.transcript.text)
        if event.synthesis_chunk and event.synthesis_chunk.is_final:
            play_audio(event.synthesis_chunk.audio_bytes)

asyncio.run(main())
```

---

## Language Support

| Language  | BCP-47   | Tier | Code-Switch Profile | Sarvam | AI4Bharat | Bhashini |
| --------- | -------- | ---- | ------------------- | ------ | --------- | -------- |
| Hindi     | `hi-IN`  | 1    | Hinglish (hi-en)    | ✅     | ✅        | ✅       |
| Tamil     | `ta-IN`  | 1    | Tanglish (ta-en)    | ✅     | ✅        | ✅       |
| Telugu    | `te-IN`  | 1    | Tenglish (te-en)    | ✅     | ✅        | ✅       |
| Bengali   | `bn-IN`  | 1    | Banglish (bn-en)    | ✅     | ✅        | ✅       |
| Marathi   | `mr-IN`  | 1    | Marathlish (mr-en)  | ✅     | ✅        | ✅       |
| Kannada   | `kn-IN`  | 2    | Kanglish (kn-en)    | ✅     | ✅        | ✅       |
| Malayalam | `ml-IN`  | 2    | Manglish (ml-en)    | ✅     | ✅        | ✅       |
| Gujarati  | `gu-IN`  | 2    | —                   | ✅     | ✅        | ✅       |
| Punjabi   | `pa-IN`  | 2    | —                   | ❌     | ✅        | ✅       |
| Odia      | `or-IN`  | 2    | —                   | ❌     | ✅        | ✅       |
| Santali   | `sat-IN` | 3    | —                   | ❌     | ❌        | ✅       |
| Manipuri  | `mni-IN` | 3    | —                   | ❌     | ❌        | ✅       |

---

## Backend Comparison

| Feature            | Sarvam AI      | AI4Bharat        | Bhashini ULCA |
| ------------------ | -------------- | ---------------- | ------------- |
| STT Streaming      | ✅ WebSocket   | ❌ Batch         | ❌ Batch      |
| TTS                | ✅ `bulbul:v2` | ❌ Stub          | ✅ REST       |
| LLM                | ✅ `sarvam-m`  | ❌               | ❌            |
| NMT                | ✅ `mayura:v1` | ✅ `IndicTrans2` | ✅ ULCA       |
| Self-hostable      | ❌             | ✅ HuggingFace   | Partial       |
| Tier A (2G)        | ✅             | ✅               | ✅            |
| Low-resource langs | ❌             | Limited          | ✅ 20+        |
| Cost               | API credits    | Self-host        | Free (MeitY)  |

---

## Transport Tiers

Vani automatically negotiates the right codec for the caller's network:

| Tier  | Network | Codec  | Sample Rate     | Use Case                     |
| ----- | ------- | ------ | --------------- | ---------------------------- |
| **A** | 2G GPRS | AMR-NB | 8 kHz           | Rural IVR, feature phones    |
| **B** | 3G      | Opus   | 16 kHz          | Smartphone apps, low-cost 4G |
| **C** | 4G/WiFi | PCM    | 16 kHz / 16-bit | Full quality, edge servers   |

```python
from vani.session import AudioProfile, SessionConfig

config = SessionConfig.for_rural("hi-IN")          # Forces Tier A
config = SessionConfig.for_language("ta-IN",       # Specify tier
    audio_profile=AudioProfile.tier_b())
```

---

## Code-Switching

Hindi-English code-switching ("Hinglish") is a first-class feature:

```
Input audio:  "मुझे ये laptop बहुत पसंद है"
               [Hindi]  [English] [Hindi⟩]

TranscriptEvent:
  text: "मुझे ये laptop बहुत पसंद है"
  code_switch_spans:
    - start_char: 8        # Unicode code-point offsets
      end_char: 14
      language_bcp47: "en"
      confidence: 0.94
```

> **Important**: Offsets are **Unicode code-point** positions, not UTF-8 byte offsets.
> `म` is 1 code point but 3 bytes in UTF-8.

---

## Protocol

Vani is defined by three Protobuf files:

| File                                                         | Purpose                                          |
| ------------------------------------------------------------ | ------------------------------------------------ |
| [`proto/vani/v1/session.proto`](proto/vani/v1/session.proto) | Session negotiation — codec, languages, backends |
| [`proto/vani/v1/stream.proto`](proto/vani/v1/stream.proto)   | Bidirectional audio/text streaming               |
| [`proto/vani/v1/action.proto`](proto/vani/v1/action.proto)   | MCP action execution over the stream             |

### Compile Stubs

```bash
pip install grpcio-tools
python -m grpc_tools.protoc \
  -I proto \
  --python_out=vani/generated \
  --grpc_python_out=vani/generated \
  --pyi_out=vani/generated \
  proto/vani/v1/session.proto \
  proto/vani/v1/stream.proto \
  proto/vani/v1/action.proto
```

---

## Action Layer (MCP)

Vani uses the **Model Context Protocol (MCP)** for tool calls. The gateway can invoke Indian-government and agritech APIs inline during a conversation:

```python
async def my_action_handler(tool_name: str, args: dict) -> str:
    if tool_name == "enam_mandi_price":
        price = await fetch_enam_price(args["crop"], args["mandi"])
        return json.dumps(price)

gateway = VaniGatewayStub(..., action_callback=my_action_handler)
```

### India Tool Registry

Pre-specified MCP tool schemas for Indian services (see [`spec/IndiaToolRegistry.md`](spec/IndiaToolRegistry.md)):

| Tool                   | Service     | Input                     |
| ---------------------- | ----------- | ------------------------- |
| `pan_validate`         | NSDL/UTI    | pan_number                |
| `aadhaar_verify_otp`   | UIDAI       | aadhaar_number            |
| `enam_mandi_price`     | eNAM        | crop, mandi               |
| `pm_kisan_eligibility` | PM-KISAN    | mobile_number, state      |
| `bhashini_translate`   | IndicTrans2 | text, src, tgt            |
| `ration_card_lookup`   | NFSA        | ration_card_number, state |

---

## Spec Documents

| Document                                                 | Contents                            |
| -------------------------------------------------------- | ----------------------------------- |
| [`spec/VAM-Overview.md`](spec/VAM-Overview.md)           | Protocol overview, four-actor model |
| [`spec/VAM-CodeSwitch.md`](spec/VAM-CodeSwitch.md)       | Code-switch annotation standard     |
| [`spec/VAM-Dialects.md`](spec/VAM-Dialects.md)           | Dialect taxonomy and routing        |
| [`spec/VAM-Transport.md`](spec/VAM-Transport.md)         | Bandwidth-adaptive transport        |
| [`spec/VAM-Actions.md`](spec/VAM-Actions.md)             | MCP action execution flow           |
| [`spec/IndiaToolRegistry.md`](spec/IndiaToolRegistry.md) | India Tool Registry schemas         |

---

## Examples

```bash
# Hinglish customer support agent
SARVAM_API_KEY=sk-... python examples/hinglish_support_agent.py

# Tamil agritech IVR (mandi price lookup)
SARVAM_API_KEY=sk-... python examples/tamil_agritech_ivr.py
```

---

## Conformance

Implementors of the VAM/1.0 protocol can validate against the YAML test suite:

```bash
ls conformance/tests/
# session_negotiation.yaml  (10 tests)
# code_switch.yaml          (10 tests)
# turn_signals.yaml         (12 tests)
```

See [`conformance/README.md`](conformance/README.md) for the conformance runner spec.

---

## Data Residency & Compliance

Vani defaults to **`DATA_RESIDENCY_INDIA_ONLY`** to comply with the **Digital Personal Data Protection (DPDP) Act, 2023**:

- Audio data never leaves Indian data centres (Sarvam/AI4Bharat servers in India)
- PII fields (`aadhaar_number`, `pan_number`) are not logged at the gateway layer
- Bhashini backend uses MeitY-hosted ULCA infrastructure

Override only when explicitly needed:

```python
from vani.session import DataResidency
config.data_residency = DataResidency.ANY   # Not recommended
```

---

## Development

```bash
git clone https://github.com/your-org/vani
cd vani
pip install -e ".[dev]"

# Run tests
pytest

# Type-check
mypy vani/

# Lint
ruff check vani/

# Regenerate proto stubs
python -m grpc_tools.protoc -I proto \
  --python_out=vani/generated --grpc_python_out=vani/generated --pyi_out=vani/generated \
  proto/vani/v1/*.proto
```

---

## Roadmap

- [ ] `v0.1.0` — Core protocol + Sarvam/AI4Bharat/Bhashini backends (current)
- [ ] `v0.2.0` — gRPC server reference implementation
- [ ] `v0.3.0` — LiveKit transport bridge
- [ ] `v0.4.0` — OpenAI Realtime API adapter
- [ ] `v0.5.0` — WebRTC gateway (browser-native)
- [ ] `v1.0.0` — Production-stable protocol

---

## Contributing

Contributions welcome! Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) (coming soon) and open an issue before submitting large PRs.

Priority areas:

- Additional language backends (Punjabi, Odia, Santali)
- Dialect-specific STT fine-tunes
- More India Tool Registry entries
- Conformance test runner CLI
- gRPC server reference implementation

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

_वाणी — Sanskrit for speech, voice, the goddess of language._  
_Built with ❤️ for Bharat._
