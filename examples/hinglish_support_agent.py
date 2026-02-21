"""
Example 1 — Hinglish Customer Support Agent

Demonstrates a complete Vani session for a Hindi+English code-switching
(Hinglish) call center use case using the Sarvam AI backend.

This example:
1. Configures a SessionConfig for Hinglish
2. Wires the VaniGatewayStub with Sarvam backends
3. Simulates a customer asking about their loan EMI status
4. Registers a `pan_validate` action (India Tool Registry)
5. Prints all TurnSignals, TranscriptEvents, and synthesis output

Usage:
    SARVAM_API_KEY=sk-... python examples/hinglish_support_agent.py

Requirements:
    pip install vani[sarvam]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# ── Vani imports ──────────────────────────────────────────────────────────────
from vani import SessionConfig
from vani.backends.sarvam import SarvamLLMBackend, SarvamSTTBackend, SarvamTTSBackend
from vani.gateway.stub import GatewayEvent, TurnState, VaniGatewayStub


def get_api_key() -> str:
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        print("Set SARVAM_API_KEY environment variable to run this example.")
        print("Get a key at: https://dashboard.sarvam.ai")
        sys.exit(1)
    return key


# ── System prompt (responds in same language as user — Hindi/Hinglish) ────────
SYSTEM_PROMPT = """
आप एक friendly loan support agent हैं।
आप Hindi और English दोनों में बात कर सकते हैं।
हमेशा user की language में respond करें।
Responses concise रखें — 2-3 sentences maximum।
अगर PAN number verify करना हो तो pan_validate tool use करें।
""".strip()


# ── Action callback: handles MCP tool calls from the LLM ─────────────────────
async def handle_action(tool_name: str, args: dict) -> str:
    """
    Simulated action executor for this example.
    In production, this would call real MCP servers.
    """
    print(f"\n  [ACTION] Tool: {tool_name}, Args: {json.dumps(args, ensure_ascii=False)}")

    if tool_name == "pan_validate":
        pan = args.get("pan_number", "")
        # Simulate NSDL/UTI response
        return json.dumps({
            "valid": True,
            "pan_type": "Individual",
            "name_on_pan": "SURESH KUMAR",
            "status": "Active",
            "masked_pan": pan[:5] + "****" + pan[-1] if len(pan) == 10 else "INVALID",
        })

    if tool_name == "enam_mandi_price":
        return json.dumps({
            "crop": args.get("crop", "wheat"),
            "mandi": args.get("mandi", "Azadpur"),
            "modal_price_per_quintal": 2310,
            "currency": "INR",
            "date": "2026-02-18",
        })

    return json.dumps({"error": f"Tool '{tool_name}' not registered in this demo"})


# ── Synthetic audio generator (simulates mic input) ───────────────────────────
async def synthetic_audio_stream(text_label: str) -> "AsyncIterator[bytes]":  # noqa: F821
    """
    Yields synthetic silent audio chunks to satisfy the STT stream interface.
    In a real integration this would be PyAudio / WebRTC audio frames.

    For a real demo, replace this with actual PCM audio bytes from a microphone
    or an audio file read with soundfile/librosa.
    """
    print(f"\n  [MIC] Simulating audio for: '{text_label}'")
    # 16kHz, 16-bit mono silence — 50 chunks of 20ms = 1 second of "audio"
    chunk = b"\x00" * 640  # 20ms of silence at 16kHz 16-bit
    for _ in range(50):
        yield chunk
        await asyncio.sleep(0.02)


# ── Stub STT that returns hardcoded transcripts (no real API call needed) ─────
class StubSTTBackend(SarvamSTTBackend):
    """
    Extends SarvamSTTBackend but returns hardcoded transcripts for the demo.
    Set SARVAM_API_KEY if you want real transcription.
    """

    DEMO_TRANSCRIPTS = [
        "मेरा loan EMI कब आएगा? मेरा PAN ABCDE1234F है",
        "क्या आप मुझे confirm कर सकते हैं?",
        "Thank you, bye",
    ]
    _call_index = 0

    async def transcribe_stream(self, audio_iter, language_hints, **kwargs):
        from vani.backends.base import TranscriptResult

        # Drain the audio iterator
        async for _ in audio_iter:
            pass

        transcript = self.DEMO_TRANSCRIPTS[
            StubSTTBackend._call_index % len(self.DEMO_TRANSCRIPTS)
        ]
        StubSTTBackend._call_index += 1

        yield TranscriptResult(
            text="",
            is_final=False,
            language_bcp47="hi-IN",
            utterance_id="demo-utt",
        )
        yield TranscriptResult(
            text=transcript,
            is_final=True,
            language_bcp47="hi-IN",
            utterance_id="demo-utt",
            confidence=0.95,
        )


async def main() -> None:
    api_key = get_api_key()

    print("━" * 60)
    print("  Vani — Hinglish Customer Support Agent Demo")
    print("  Language: Hindi + English (Hinglish)")
    print("  Backend: Sarvam AI")
    print("━" * 60)

    # ── Build session config ─────────────────────────────────────────────────
    config = SessionConfig.for_hinglish(
        caller_id="+91-9876543210",
        metadata={"channel": "ivr", "use_case": "loan_support"},
    )
    print(f"\n[SESSION] {config}")

    # ── Wire the gateway ─────────────────────────────────────────────────────
    gateway = VaniGatewayStub(
        config=config,
        stt=StubSTTBackend(api_key=api_key),
        llm=SarvamLLMBackend(api_key=api_key),
        tts=SarvamTTSBackend(api_key=api_key),
        system_prompt=SYSTEM_PROMPT,
        action_callback=handle_action,
    )
    print(f"\n[GATEWAY] {gateway}")

    # ── Simulate 3 conversation turns ────────────────────────────────────────
    for turn_num in range(1, 4):
        print(f"\n{'═' * 60}")
        print(f"  TURN {turn_num}")
        print("═" * 60)

        audio_iter = synthetic_audio_stream(f"turn {turn_num}")

        async for event in gateway.process_audio(audio_iter):
            _handle_event(event)

    print("\n" + "━" * 60)
    print("  Demo complete.")
    print("━" * 60)


def _handle_event(event: GatewayEvent) -> None:
    if event.turn_signal:
        sig = event.turn_signal
        icon = {
            TurnState.IDLE: "⬜",
            TurnState.LISTENING: "🎙 ",
            TurnState.THINKING: "🧠",
            TurnState.SPEAKING: "🔊",
            TurnState.INTERRUPTED: "✋",
            TurnState.END_OF_TURN: "✅",
            TurnState.ERROR: "❌",
        }.get(sig.event, "❓")
        print(f"  [TURN] {icon} {sig.event.value}")

    if event.transcript:
        t = event.transcript
        label = "FINAL" if t.is_final else "partial"
        print(f"  [ASR {label}] {t.text!r}")
        if t.code_switch_spans:
            for span in t.code_switch_spans:
                word = t.text[span.start_char:span.end_char]
                print(f"    ↳ code-switch: '{word}' → {span.language_bcp47} (conf={span.confidence:.2f})")

    if event.synthesis_chunk:
        chunk = event.synthesis_chunk
        status = "FINAL" if chunk.is_final else f"chunk {chunk.chunk_index}"
        print(f"  [TTS {status}] {len(chunk.audio_bytes)} bytes")

    if event.error:
        print(f"  [ERROR] {event.error}")


if __name__ == "__main__":
    asyncio.run(main())
