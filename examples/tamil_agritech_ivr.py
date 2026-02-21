"""
Example 2 — Tamil Agritech IVR Agent

Demonstrates a Vani session for a Tamil-language agricultural advisory IVR:
- Farmer calls in from a 3G mobile (Tier B audio profile)
- Asks about mandi price for tomatoes in Koyambedu market (Chennai)
- Agent fetches real-time price via the `enam_mandi_price` registry tool
- Responds in Tamil

This example also demonstrates:
- Bhashini NMT as fallback translation backend
- Dialect routing (Coimbatore Tamil vs. Chennai Tamil)
- Tier B AudioProfile (Opus 16kHz for 3G)

Usage:
    SARVAM_API_KEY=sk-... python examples/tamil_agritech_ivr.py

Requirements:
    pip install vani[sarvam]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from vani import SessionConfig
from vani.backends.sarvam import SarvamLLMBackend, SarvamSTTBackend, SarvamTTSBackend
from vani.gateway.stub import GatewayEvent, TurnState, VaniGatewayStub
from vani.session import AudioProfile


def get_api_key() -> str:
    key = os.environ.get("SARVAM_API_KEY", "")
    if not key:
        print("Set SARVAM_API_KEY environment variable to run this example.")
        sys.exit(1)
    return key


SYSTEM_PROMPT = """
நீங்கள் ஒரு விவசாய ஆலோசனை AI ஆவீர்கள்.
விவசாயிகளுக்கு மண்டி விலைகள், பயிர் ஆலோசனைகள் வழங்குகிறீர்கள்.
எப்போதும் Tamil-இல் பதில் சொல்லுங்கள்.
சுருக்கமாக — 2 sentences மட்டும்.
மண்டி விலை கேட்டால் enam_mandi_price tool use பண்ணுங்கள்.
""".strip()


# ── Action handler ─────────────────────────────────────────────────────────
async def handle_action(tool_name: str, args: dict) -> str:
    print(f"\n  [ACTION] {tool_name}({json.dumps(args, ensure_ascii=False)})")

    if tool_name == "enam_mandi_price":
        crop = args.get("crop", "tomato")
        mandi = args.get("mandi", "Koyambedu")
        # Simulated eNAM response
        price_data = {
            "tomato": {"min": 800, "max": 1200, "modal": 1000},
            "onion": {"min": 400, "max": 600, "modal": 500},
            "rice": {"min": 2200, "max": 2500, "modal": 2350},
        }.get(crop.lower(), {"min": 500, "max": 800, "modal": 650})

        return json.dumps({
            "crop": crop,
            "crop_tamil": {
                "tomato": "தக்காளி", "onion": "வெங்காயம்", "rice": "அரிசி"
            }.get(crop.lower(), crop),
            "mandi": mandi,
            "state": "Tamil Nadu",
            "min_price_per_quintal": price_data["min"],
            "max_price_per_quintal": price_data["max"],
            "modal_price_per_quintal": price_data["modal"],
            "currency": "INR",
            "date": "2026-02-18",
            "source": "eNAM (demo)",
        })

    return json.dumps({"error": f"Tool not available: {tool_name}"})


# ── Stub STT for demo ──────────────────────────────────────────────────────
class TamilStubSTT(SarvamSTTBackend):
    DEMO_TRANSCRIPTS = [
        "கோயம்பேடு மார்க்கெட்டில் இன்று தக்காளி விலை என்ன?",
        "நன்றி. வேறு ஏதாவது மண்டி விலை தெரியுமா?",
    ]
    _idx = 0

    async def transcribe_stream(self, audio_iter, language_hints, **kwargs):
        from vani.backends.base import TranscriptResult

        async for _ in audio_iter:
            pass

        text = self.DEMO_TRANSCRIPTS[TamilStubSTT._idx % len(self.DEMO_TRANSCRIPTS)]
        TamilStubSTT._idx += 1

        yield TranscriptResult(
            text=text, is_final=True, language_bcp47="ta-IN",
            utterance_id="tamil-demo", confidence=0.93,
            dialect_tag="ta-IN-Chennai-Colloquial",
        )


async def synthetic_audio(label: str):
    print(f"\n  [MIC] {label}")
    for _ in range(50):
        yield b"\x00" * 640
        await asyncio.sleep(0.02)


async def main() -> None:
    api_key = get_api_key()

    print("━" * 60)
    print("  Vani — Tamil Agritech IVR Demo")
    print("  Language: Tamil (ta-IN)")
    print("  Transport: Tier B (Opus 16kHz — 3G profile)")
    print("  Backend: Sarvam AI")
    print("━" * 60)

    # Tier B config — Opus 16kHz for 3G rural network
    config = SessionConfig.for_language(
        "ta-IN",
        caller_id="+91-44-12345678",
        audio_profile=AudioProfile.tier_b(),
        metadata={"channel": "ivr", "use_case": "agritech", "district": "Chennai"},
    )
    config.capabilities.dialect_routing = True  # Enable dialect detection

    print(f"\n[SESSION] id={config.session_id[:8]}...")
    print(f"  language=ta-IN | codec={config.audio_profile.codec.value}")
    print(f"  dialect_routing={config.capabilities.dialect_routing}")

    gateway = VaniGatewayStub(
        config=config,
        stt=TamilStubSTT(api_key=api_key),
        llm=SarvamLLMBackend(api_key=api_key),
        tts=SarvamTTSBackend(api_key=api_key),
        system_prompt=SYSTEM_PROMPT,
        action_callback=handle_action,
    )

    for turn_num in range(1, 3):
        print(f"\n{'═' * 60}  TURN {turn_num}  {'═' * 60}")

        async for event in gateway.process_audio(
            synthetic_audio(f"farmer query {turn_num}")
        ):
            if event.turn_signal:
                icons = {
                    TurnState.LISTENING: "🎙 LISTENING",
                    TurnState.THINKING: "🧠 THINKING",
                    TurnState.SPEAKING: "🔊 SPEAKING",
                    TurnState.END_OF_TURN: "✅ END_OF_TURN",
                    TurnState.ERROR: "❌ ERROR",
                }
                print(f"  [TURN] {icons.get(event.turn_signal.event, event.turn_signal.event.value)}")

            if event.transcript and event.transcript.is_final:
                t = event.transcript
                print(f"  [FARMER SAYS] {t.text}")
                if t.dialect_tag:
                    print(f"    ↳ Detected dialect: {t.dialect_tag}")

            if event.synthesis_chunk and event.synthesis_chunk.is_final:
                print(f"  [AGENT SPEAKS] {len(event.synthesis_chunk.audio_bytes)} bytes of Tamil TTS")

    print("\n" + "━" * 60)
    print("  IVR session complete.")
    print("━" * 60)


if __name__ == "__main__":
    asyncio.run(main())
