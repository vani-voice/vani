#!/usr/bin/env python3
"""
demo/live_cli.py — Real-time Vani CLI Demo
==========================================
Records from your microphone, runs through the full Vani pipeline
(Sarvam STT → LLM → TTS), and plays back audio through your speakers.

Features demonstrated:
  ✅ Hinglish (Hindi+English) code-switch detection + highlighting
  ✅ Turn state machine (LISTENING → THINKING → SPEAKING)
  ✅ India Tool Registry: enam_mandi_price, pan_validate
  ✅ Multi-turn conversation with history

Usage:
    export SARVAM_API_KEY=sk-...
    python demo/live_cli.py

    # Optional flags:
    python demo/live_cli.py --lang ta-IN          # Tamil
    python demo/live_cli.py --lang hi-IN --rural  # 2G AMR-NB codec
    python demo/live_cli.py --turns 5             # How many turns to record
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import sys
import threading
import time
from typing import AsyncIterator

import numpy as np
import sounddevice as sd
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

# Ensure the project root is on sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vani.backends.base import TranscriptResult
from vani.backends.sarvam import SarvamLLMBackend, SarvamSTTBackend, SarvamTTSBackend
from vani.gateway.stub import GatewayEvent, TurnState, VaniGatewayStub
from vani.session import AudioCodec, AudioProfile, SessionConfig

console = Console()

# ── Audio constants ──────────────────────────────────────────────────────────
SAMPLE_RATE = 16_000        # Hz
CHANNELS = 1
CHUNK_FRAMES = 320          # 20ms at 16kHz
DTYPE = "int16"
SILENCE_THRESHOLD = 500     # RMS below this = silence (set above ambient noise)
SILENCE_DURATION_S = 1.5    # Seconds of silence to trigger end-of-utterance
MIN_RECORD_S = 1.0          # Minimum recording time before silence detection


# ── Tool implementations ─────────────────────────────────────────────────────

async def handle_tool(tool_name: str, args: dict) -> str:
    """Simulate real Indian API tool calls."""
    console.print(f"\n  [bold yellow]⚡ TOOL CALL:[/] [cyan]{tool_name}[/]", args)

    if tool_name == "enam_mandi_price":
        crop = args.get("crop", "unknown")
        mandi = args.get("mandi", "unknown")
        await asyncio.sleep(0.3)  # Simulate API latency
        prices = {
            "tomato":  {"min": 800,  "max": 1200, "modal": 1000},
            "onion":   {"min": 400,  "max": 600,  "modal": 500},
            "rice":    {"min": 2200, "max": 2500,  "modal": 2350},
            "wheat":   {"min": 1800, "max": 2100,  "modal": 1950},
            "cotton":  {"min": 5500, "max": 6000,  "modal": 5750},
            "potato":  {"min": 600,  "max": 900,   "modal": 750},
        }
        data = prices.get(crop.lower(), {"min": 500, "max": 800, "modal": 650})
        result = json.dumps({
            "crop": crop,
            "mandi": mandi,
            "state": "Auto-detected",
            "min_price_per_quintal_inr": data["min"],
            "max_price_per_quintal_inr": data["max"],
            "modal_price_per_quintal_inr": data["modal"],
            "date": "2026-02-18",
            "source": "eNAM (demo)",
        })
        console.print(f"  [bold green]✓ TOOL RESULT:[/] {result[:120]}")
        return result

    if tool_name == "pan_validate":
        pan = args.get("pan_number", "")
        await asyncio.sleep(0.2)
        import re
        valid = bool(re.match(r"[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan))
        result = json.dumps({
            "pan_number": pan,
            "is_valid_format": valid,
            "message": "Valid PAN format" if valid else "Invalid PAN format",
        })
        console.print(f"  [bold green]✓ TOOL RESULT:[/] {result}")
        return result

    if tool_name == "bhashini_translate":
        text = args.get("text", "")
        src = args.get("source_language", "hi-IN")
        tgt = args.get("target_language", "en")
        await asyncio.sleep(0.4)
        result = json.dumps({
            "translated_text": f"[Translated: {text}]",
            "source": src,
            "target": tgt,
            "model": "indictrans2-demo",
        })
        console.print(f"  [bold green]✓ TOOL RESULT:[/] {result[:120]}")
        return result

    return json.dumps({"error": f"Tool not available: {tool_name}"})


# ── Mic recorder ─────────────────────────────────────────────────────────────

class MicRecorder:
    """
    Records from the default mic, buffers chunks, and detects end-of-utterance
    via trailing silence. Yields PCM bytes asynchronously.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._q: queue.Queue[bytes | None] = queue.Queue()
        self._stream: sd.InputStream | None = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            console.print(f"[yellow]Mic status: {status}[/]")
        self._q.put(indata.tobytes())

    def start(self) -> None:
        # Clear any leftover sentinel from a previous stop()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_FRAMES,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._q.put(None)  # Sentinel

    async def utterance_stream(self) -> AsyncIterator[bytes]:
        """
        Yields audio chunks starting from speech onset until trailing silence.

        Phase 1 – Wait for speech:
          Buffer chunks silently. Once RMS exceeds SILENCE_THRESHOLD, yield
          the recent pre-speech buffer (to capture the word onset) and move
          to phase 2. Gives up after MAX_WAIT_S seconds of silence.

        Phase 2 – Stream until trailing silence:
          Yield chunks in real-time. Stops after SILENCE_DURATION_S of
          continuous quiet (only after MIN_RECORD_S of streaming).
        """
        loop = asyncio.get_event_loop()
        silence_chunks = int(SILENCE_DURATION_S * self.sample_rate / CHUNK_FRAMES)
        min_speech_chunks = int(MIN_RECORD_S * self.sample_rate / CHUNK_FRAMES)

        # ── Phase 1: buffer until speech detected ────────────────────────
        PRE_SPEECH_S = 0.3          # keep 300 ms before speech onset
        pre_max = max(1, int(PRE_SPEECH_S * self.sample_rate / CHUNK_FRAMES))
        pre_buffer: list[bytes] = []

        MAX_WAIT_S = 15.0           # give the user up to 15 s to begin
        max_wait = int(MAX_WAIT_S * self.sample_rate / CHUNK_FRAMES)
        waited = 0

        while True:
            chunk = await loop.run_in_executor(None, self._q.get)
            if chunk is None:
                return                      # recorder stopped
            waited += 1

            pre_buffer.append(chunk)
            if len(pre_buffer) > pre_max:
                pre_buffer.pop(0)

            rms = float(np.sqrt(np.mean(
                np.frombuffer(chunk, dtype=np.int16).astype(float) ** 2
            )))
            if rms > SILENCE_THRESHOLD:
                # Speech detected — flush pre-buffer and move to phase 2
                for c in pre_buffer:
                    yield c
                pre_buffer.clear()
                break

            if waited >= max_wait:
                return                      # timed out waiting for speech

        # ── Phase 2: stream until trailing silence ───────────────────────
        streamed = len(pre_buffer)  # chunks already yielded
        silent_count = 0

        while True:
            chunk = await loop.run_in_executor(None, self._q.get)
            if chunk is None:
                break
            yield chunk
            streamed += 1

            rms = float(np.sqrt(np.mean(
                np.frombuffer(chunk, dtype=np.int16).astype(float) ** 2
            )))
            if rms > SILENCE_THRESHOLD:
                silent_count = 0
            else:
                if streamed >= min_speech_chunks:
                    silent_count += 1
                    if silent_count >= silence_chunks:
                        break


# ── TTS player ───────────────────────────────────────────────────────────────

def play_pcm(audio_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    """Play raw 16-bit PCM audio on the default output device."""
    try:
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(audio, samplerate=sample_rate, blocking=True)
    except Exception as exc:
        console.print(f"[yellow]TTS playback error: {exc}[/]")


# ── Transcript renderer ──────────────────────────────────────────────────────

def render_transcript(t: TranscriptResult) -> Text:
    """Render a transcript with code-switch spans highlighted in a different colour."""
    text = Text()
    src = t.text
    spans = t.code_switch_spans or []
    spans = sorted(spans, key=lambda s: s.start_char)

    pos = 0
    for span in spans:
        if pos < span.start_char:
            text.append(src[pos:span.start_char], style="white")
        text.append(
            src[span.start_char:span.end_char],
            style=f"bold magenta",
        )
        text.append(
            f" [{span.language_bcp47} {span.confidence:.0%}]",
            style="dim magenta",
        )
        pos = span.end_char
    if pos < len(src):
        text.append(src[pos:], style="white")
    return text


# ── Main demo loop ───────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "hi-IN": (
        "आप एक helpful AI assistant हैं। Hindi और English दोनों में बात कर सकते हैं। "
        "मंडी की कीमतें जानने के लिए enam_mandi_price tool use करें। "
        "PAN card validate करने के लिए pan_validate tool। "
        "हमेशा 2-3 sentences में जवाब दो।"
    ),
    "ta-IN": (
        "நீங்கள் ஒரு helpful AI assistant. Tamil மற்றும் English பேசலாம். "
        "மண்டி விலைகளுக்கு enam_mandi_price tool பயன்படுத்துங்கள். "
        "2-3 வாக்கியங்களில் பதில் சொல்லுங்கள்."
    ),
    "te-IN": (
        "మీరు ఒక helpful AI assistant. Telugu మరియు English మాట్లాడవచ్చు. "
        "మండీ ధరల కోసం enam_mandi_price tool వాడండి. "
        "2-3 వాక్యాలలో జవాబు ఇవ్వండి."
    ),
    "bn-IN": (
        "আপনি একটি helpful AI assistant। বাংলা এবং English দুটোতেই কথা বলতে পারেন। "
        "মান্ডি দাম জানতে enam_mandi_price tool ব্যবহার করুন। "
        "২-৩ বাক্যে উত্তর দিন।"
    ),
}
DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPTS["hi-IN"]


async def run_demo(
    api_key: str,
    language: str = "hi-IN",
    rural: bool = False,
    num_turns: int = 3,
) -> None:
    audio_profile = AudioProfile.tier_a() if rural else AudioProfile.tier_c()

    if language == "hi-IN":
        config = SessionConfig.for_hinglish(caller_id="live-demo")
    else:
        config = SessionConfig.for_language(language)

    config.audio_profile = audio_profile

    system_prompt = SYSTEM_PROMPTS.get(language, DEFAULT_SYSTEM_PROMPT)

    gateway = VaniGatewayStub(
        config=config,
        stt=SarvamSTTBackend(api_key=api_key),
        llm=SarvamLLMBackend(api_key=api_key),
        tts=SarvamTTSBackend(api_key=api_key),
        system_prompt=system_prompt,
        action_callback=handle_tool,
        max_history_turns=6,
    )

    console.print(Panel.fit(
        f"[bold green]🎙  Vani Live Demo[/]\n"
        f"Language : [cyan]{language}[/]  |  "
        f"Codec    : [cyan]{audio_profile.codec.value}[/]\n"
        f"Session  : [dim]{config.session_id[:8]}...[/]\n\n"
        f"[bold]Try asking:[/]\n"
        f"  • [italic]Koyambedu mandi mein aaj tomato ka bhav kya hai?[/]\n"
        f"  • [italic]Mera PAN ABCDE1234F valid hai kya?[/]\n"
        f"  • [italic]What is the price of wheat in APMC Mumbai?[/]\n\n"
        f"[dim]Speak after the 🔴 prompt. Silence for {SILENCE_DURATION_S}s ends the turn.[/]",
        title="[bold white]VAM/1.0 Protocol[/]",
        border_style="green",
    ))

    recorder = MicRecorder()

    tts_buffer: list[bytes] = []

    for turn in range(1, num_turns + 1):
        console.rule(f"[bold]Turn {turn} of {num_turns}[/]")
        console.print("[bold red]🔴 Listening...[/] (speak now, pause to end)")

        recorder.start()
        tts_buffer.clear()
        start_ts = time.perf_counter()

        try:
            async for event in gateway.process_audio(recorder.utterance_stream()):
                _handle_event(event, tts_buffer, start_ts)
        finally:
            recorder.stop()

        # Play all accumulated TTS audio
        if tts_buffer:
            full_audio = b"".join(tts_buffer)
            console.print(f"\n[bold green]🔊 Playing TTS[/] ({len(full_audio) // 1000}KB audio)...")
            play_pcm(full_audio)

        if turn < num_turns:
            console.print("\n[dim]Ready for next turn in 1s...[/]")
            await asyncio.sleep(1.0)

    console.print("\n[bold green]✅ Demo complete![/]")


def _handle_event(
    event: GatewayEvent,
    tts_buffer: list[bytes],
    start_ts: float,
) -> None:
    elapsed = (time.perf_counter() - start_ts) * 1000

    if event.turn_signal:
        icons = {
            TurnState.LISTENING:   "🎙  LISTENING",
            TurnState.THINKING:    "🧠  THINKING",
            TurnState.SPEAKING:    "🔊  SPEAKING",
            TurnState.END_OF_TURN: "✅  END_OF_TURN",
            TurnState.IDLE:        "💤  IDLE",
            TurnState.INTERRUPTED: "⚡  INTERRUPTED",
            TurnState.ERROR:       "❌  ERROR",
        }
        label = icons.get(event.turn_signal.event, str(event.turn_signal.event))
        console.print(f"  [{elapsed:6.0f}ms] [bold]{label}[/]")

    if event.transcript:
        t = event.transcript
        kind = "[bold green]FINAL[/]" if t.is_final else "[dim]partial[/]"
        spans = t.code_switch_spans or []
        rendered = render_transcript(t)
        prefix = f"  [{elapsed:6.0f}ms] 📝 {kind}  "
        console.print(prefix, end="")
        console.print(rendered)
        if t.is_final and spans:
            console.print(
                f"           [dim]Code-switches detected: {len(spans)} span(s)[/]"
            )
        if t.is_final and t.dialect_tag:
            console.print(f"           [dim]Dialect: {t.dialect_tag}[/]")

    if event.synthesis_chunk:
        chunk = event.synthesis_chunk
        if chunk.audio_bytes:
            tts_buffer.append(chunk.audio_bytes)

    if event.error:
        console.print(f"  [bold red]❌ ERROR:[/] {event.error}")


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vani real-time CLI demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--lang",
        default="hi-IN",
        choices=["hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN"],
        help="Primary language (default: hi-IN Hinglish)",
    )
    parser.add_argument(
        "--rural",
        action="store_true",
        help="Use Tier A (AMR-NB 8kHz) profile — simulates 2G rural connection",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=3,
        help="Number of conversation turns (default: 3)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("SARVAM_API_KEY", "")
    if not api_key:
        console.print("[bold red]Error:[/] Set SARVAM_API_KEY environment variable.")
        console.print("  export SARVAM_API_KEY=sk-...")
        sys.exit(1)

    # Check mic availability
    try:
        device_info = sd.query_devices(kind="input")
        console.print(f"[dim]Mic: {device_info['name']}[/]")
    except Exception:
        console.print("[bold red]Error:[/] No input device found.")
        sys.exit(1)

    asyncio.run(run_demo(
        api_key=api_key,
        language=args.lang,
        rural=args.rural,
        num_turns=args.turns,
    ))


if __name__ == "__main__":
    main()
