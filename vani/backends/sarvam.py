"""
Sarvam AI backend implementation for Vani.

Implements VamSTTBackend, VamTTSBackend, and VamLLMBackend using:
  - Sarvam Saaras v3 (WebSocket streaming STT)
  - Sarvam Bulbul v2/v3 (TTS)
  - Sarvam-M (LLM)

Documentation: https://docs.sarvam.ai

Install: pip install vani[sarvam]
"""

from __future__ import annotations

import base64
import io
import json
import uuid
import wave
from typing import AsyncIterator

try:
    import httpx
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError as e:
    raise ImportError(
        "Sarvam backend requires 'httpx' and 'websockets'. "
        "Install with: pip install vani[sarvam]"
    ) from e

from vani.backends.base import (
    CodeSwitchSpan,
    LLMResult,
    NMTResult,
    SynthesisResult,
    TranscriptResult,
    VamLLMBackend,
    VamNMTBackend,
    VamSTTBackend,
    VamTTSBackend,
)

# Sarvam API base URL
SARVAM_API_BASE = "https://api.sarvam.ai"
SARVAM_STT_WS_BASE = "wss://api.sarvam.ai/speech-to-text/ws"
SARVAM_TTS_URL = f"{SARVAM_API_BASE}/text-to-speech"
SARVAM_LLM_URL = f"{SARVAM_API_BASE}/v1/chat/completions"
SARVAM_TRANSLATE_URL = f"{SARVAM_API_BASE}/translate"

# Sarvam Saaras v3 supported languages (BCP-47)
SAARAS_LANGUAGES = [
    "hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN",
    "kn-IN", "ml-IN", "gu-IN", "pa-IN", "or-IN", "en-IN",
]


class SarvamSTTBackend(VamSTTBackend):
    """
    Sarvam Saaras v3 streaming STT backend.

    Features:
    - Real-time WebSocket streaming (target <250ms first-token latency)
    - Native code-switch / code-mixing support
    - Auto language detection (no hint required, but hints improve accuracy)
    - Telephony-grade 8kHz support for Tier A sessions

    Usage::

        backend = SarvamSTTBackend(api_key="your-sarvam-api-key")
        async for transcript in backend.transcribe_stream(audio_iter, ["hi-IN"]):
            print(transcript.text, transcript.code_switch_spans)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "saaras:v3",
        enable_timestamps: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._enable_timestamps = enable_timestamps

    @property
    def backend_name(self) -> str:
        return f"Sarvam {self._model}"

    @property
    def supported_languages(self) -> list[str]:
        return SAARAS_LANGUAGES

    @property
    def supports_code_switching(self) -> bool:
        return True  # Saaras v3 natively handles code-mixing

    async def transcribe_stream(
        self,
        audio_iter: AsyncIterator[bytes],
        language_hints: list[str],
        *,
        session_id: str = "",
        code_switch: bool = False,
        dialect_routing: bool = False,
    ) -> AsyncIterator[TranscriptResult]:
        """
        Stream audio bytes to Sarvam Saaras v3 and yield transcript events.

        Waits for the first audio chunk before opening the WebSocket so that
        the caller can do client-side VAD without burning server time on silence.
        """
        import asyncio
        import urllib.parse

        utterance_id = str(uuid.uuid4())
        language_code = language_hints[0] if language_hints else "hi-IN"

        # ── Wait for first audio chunk (allows client-side VAD) ──────────
        first_chunk: bytes | None = None
        async for chunk in audio_iter:
            first_chunk = chunk
            break
        if first_chunk is None:
            return  # No audio produced at all

        async def _chained_audio() -> AsyncIterator[bytes]:
            """Prepend the first chunk back onto the remaining iterator."""
            yield first_chunk  # type: ignore[misc]
            async for c in audio_iter:
                yield c

        # Build URL with query params (no input_audio_codec — using WAV JSON)
        params = {
            "language-code": language_code,
            "model": self._model,
        }
        ws_url = SARVAM_STT_WS_BASE + "?" + urllib.parse.urlencode(params)

        # Auth header uses title-cased key (required by Sarvam API)
        headers = {"Api-Subscription-Key": self._api_key}

        try:
            async with websockets.connect(
                ws_url, additional_headers=headers
            ) as ws:
                # Stream audio concurrently with receiving events.
                send_task = asyncio.create_task(
                    self._send_audio(ws, _chained_audio())
                )

                try:
                    while True:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                        except asyncio.TimeoutError:
                            break
                        if isinstance(raw, bytes):
                            continue
                        event = json.loads(raw)
                        result = self._parse_sarvam_event(
                            event, utterance_id, language_code, code_switch
                        )
                        if result is not None:
                            yield result
                except ConnectionClosed:
                    pass
                finally:
                    send_task.cancel()
                    try:
                        await send_task
                    except (asyncio.CancelledError, ConnectionClosed):
                        pass

        except ConnectionClosed:
            pass  # connection closed cleanly with no transcript

        except Exception as exc:
            yield TranscriptResult(
                text=f"[STT_ERROR: {exc}]",
                is_final=True,
                language_bcp47=language_hints[0] if language_hints else "hi-IN",
                utterance_id=utterance_id,
                confidence=0.0,
            )

    @staticmethod
    def _pcm_to_wav_b64(pcm: bytes, sample_rate: int = 16000) -> str:
        """Convert raw PCM to base64-encoded WAV string."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return base64.b64encode(buf.getvalue()).decode()

    async def _send_audio(
        self, ws: "websockets.WebSocketClientProtocol", audio_iter: AsyncIterator[bytes]
    ) -> None:
        """Send audio as JSON AudioMessage (base64-encoded WAV), then flush."""
        try:
            buffer = bytearray()
            # Buffer ~500ms of audio per message (8000 samples × 2 bytes = 16000)
            chunk_size = 16000
            async for chunk in audio_iter:
                if chunk:
                    buffer.extend(chunk)
                    while len(buffer) >= chunk_size:
                        wav_b64 = self._pcm_to_wav_b64(bytes(buffer[:chunk_size]))
                        msg = json.dumps({
                            "audio": {
                                "data": wav_b64,
                                "sample_rate": 16000,
                                "encoding": "audio/wav",
                            }
                        })
                        await ws.send(msg)
                        buffer = buffer[chunk_size:]
            # Send remaining audio
            if buffer:
                wav_b64 = self._pcm_to_wav_b64(bytes(buffer))
                msg = json.dumps({
                    "audio": {
                        "data": wav_b64,
                        "sample_rate": 16000,
                        "encoding": "audio/wav",
                    }
                })
                await ws.send(msg)
            # Signal end-of-stream
            await ws.send(json.dumps({"type": "flush"}))
        except ConnectionClosed:
            pass  # server closed before we finished sending

    def _parse_sarvam_event(
        self,
        event: dict,
        utterance_id: str,
        language_code: str,
        code_switch: bool,
    ) -> TranscriptResult | None:
        """
        Convert a Sarvam WebSocket event to a Vani TranscriptResult.

        Sarvam response envelope: {"type": "data"|"events"|"error", "data": {...}}
        - type="data": transcription result with .transcript, .language_code, etc.
        - type="events": VAD event (speech start/end) — skip
        - type="error": error payload — raise
        """
        msg_type = event.get("type", "")

        if msg_type == "error":
            err = event.get("data", {})
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
            # "Error in Pipeline : 'text'" means no speech detected — treat as empty
            if "Pipeline" in msg:
                return None
            raise RuntimeError(f"Sarvam STT error: {err}")

        if msg_type == "events":
            # VAD signal (speech start/end) — not a transcript, skip
            return None

        if msg_type == "data":
            data = event.get("data", {})
            transcript_text = data.get("transcript", "")
            detected_lang = data.get("language_code") or language_code
            confidence = data.get("language_probability") or 0.9
            spans: list[CodeSwitchSpan] = []

            if code_switch and "timestamps" in data and data["timestamps"]:
                # Sarvam may embed word-level info in timestamps dict
                words = data["timestamps"].get("words", [])
                if words:
                    spans = self._extract_code_switch_spans(
                        transcript_text, words, language_code
                    )

            return TranscriptResult(
                text=transcript_text,
                is_final=True,  # Sarvam streaming returns final transcripts
                language_bcp47=detected_lang,
                utterance_id=utterance_id,
                confidence=float(confidence),
                code_switch_spans=spans,
            )

        return None  # Unknown event type; skip

    def _extract_code_switch_spans(
        self, text: str, words: list[dict], base_language: str
    ) -> list[CodeSwitchSpan]:
        """
        Extract CodeSwitchSpan objects from Sarvam word-level annotations.

        Sarvam's word objects carry a `language` field when code-mixing is
        detected. Any word whose language differs from the base language
        is annotated as a span.
        """
        spans = []
        cursor = 0

        for word_info in words:
            word = word_info.get("word", "")
            word_lang = word_info.get("language", base_language)

            # Find this word's position in the transcript
            pos = text.find(word, cursor)
            if pos == -1:
                continue

            if word_lang != base_language:
                spans.append(
                    CodeSwitchSpan(
                        start_char=pos,
                        end_char=pos + len(word),
                        language_bcp47=word_lang,
                        confidence=word_info.get("confidence", 0.9),
                    )
                )
            cursor = pos + len(word)

        return spans

    async def health_check(self) -> bool:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{SARVAM_API_BASE}/health",
                    headers={"Api-Subscription-Key": self._api_key},
                    timeout=5.0,
                )
                return resp.status_code == 200
            except Exception:
                return False


# ─────────────────────────────────────────────────────────────────────────────


class SarvamTTSBackend(VamTTSBackend):
    """
    Sarvam Bulbul v2/v3 TTS backend.

    Supports 11 Indian languages with contact-center-grade voice quality.
    Streaming is emulated by chunking the Sarvam REST response into frames
    (Sarvam's streaming TTS API is WebSocket-based in v3 — add WS path here
    when their streaming endpoint is GA).
    """

    # Default voice IDs — Bulbul v3 voices (pan-language, 30+ options)
    # v3: shubh (default), aditya, ritu, priya, neha, rahul, pooja, rohan, simran, kavya...
    # v2: anushka, manisha, vidya, arya (female); abhilash, karun, hitesh (male)
    DEFAULT_VOICES: dict[str, str] = {
        "hi-IN": "shubh",
        "ta-IN": "shubh",
        "te-IN": "shubh",
        "bn-IN": "shubh",
        "mr-IN": "shubh",
        "kn-IN": "shubh",
        "ml-IN": "shubh",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "bulbul:v3",
    ) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def backend_name(self) -> str:
        return f"Sarvam {self._model}"

    @property
    def supported_languages(self) -> list[str]:
        return list(self.DEFAULT_VOICES.keys())

    async def synthesize_stream(
        self,
        text: str,
        language_bcp47: str,
        *,
        voice_id: str = "",
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        output_codec: str = "PCM_16K_16",
        session_id: str = "",
    ) -> AsyncIterator[SynthesisResult]:
        """
        Request synthesis from Sarvam and yield audio chunks.

        Sarvam's REST TTS returns the full audio in one response;
        we chunk it into 40ms frames for streaming playback.
        """
        voice = voice_id or self.DEFAULT_VOICES.get(language_bcp47, "meera")

        # bulbul:v3 does NOT support pitch or loudness; only v2 does
        payload: dict = {
            "text": text,
            "target_language_code": language_bcp47,
            "speaker": voice,
            "model": self._model,
            "pace": speaking_rate,
            "enable_preprocessing": True,
        }
        if "v2" in self._model:
            payload["pitch"] = pitch
            payload["loudness"] = 1.0

        headers = {
            "Api-Subscription-Key": self._api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(SARVAM_TTS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Sarvam returns base64-encoded WAV / PCM
        import base64

        audio_b64 = data.get("audios", [""])[0]
        audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

        # Chunk into ~40ms PCM frames (16kHz, 16-bit mono = 1280 bytes/40ms)
        chunk_size = 1280
        total = len(audio_bytes)
        for i, offset in enumerate(range(0, total, chunk_size)):
            chunk = audio_bytes[offset : offset + chunk_size]
            is_final = (offset + chunk_size) >= total
            yield SynthesisResult(
                audio_bytes=chunk,
                codec=output_codec,
                is_final=is_final,
                duration_ms=40,
                chunk_index=i,
            )


# ─────────────────────────────────────────────────────────────────────────────


class SarvamLLMBackend(VamLLMBackend):
    """
    Sarvam-M LLM backend.

    Sarvam-M supports Indian languages natively and is free per token
    in the Sarvam API (as of Feb 2026). Uses an OpenAI-compatible
    chat completions endpoint with streaming support.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "sarvam-m",
    ) -> None:
        self._api_key = api_key
        self._model = model

    @property
    def backend_name(self) -> str:
        return f"Sarvam {self._model}"

    @property
    def supported_languages(self) -> list[str]:
        return SAARAS_LANGUAGES

    async def chat_stream(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        language_hint: str = "hi-IN",
        session_id: str = "",
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncIterator[LLMResult]:
        """Stream a chat completion from Sarvam-M."""
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        headers = {
            "Api-Subscription-Key": self._api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", SARVAM_LLM_URL, json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield LLMResult(text_delta="", is_final=True, finish_reason="stop")
                        return
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason", "")

                    # Tool call delta
                    tool_calls = delta.get("tool_calls") if delta else None
                    if tool_calls:
                        yield LLMResult(
                            text_delta="",
                            is_final=False,
                            tool_call=tool_calls[0],
                            finish_reason=finish_reason or "",
                        )
                    else:
                        yield LLMResult(
                            text_delta=delta.get("content", ""),
                            is_final=bool(finish_reason),
                            finish_reason=finish_reason or "",
                        )


# ─────────────────────────────────────────────────────────────────────────────


class SarvamNMTBackend(VamNMTBackend):
    """
    Sarvam Mayura / IndicTrans2 translation backend.
    """

    SUPPORTED_PAIRS = [
        (src, tgt)
        for src in SAARAS_LANGUAGES
        for tgt in SAARAS_LANGUAGES
        if src != tgt
    ]

    def __init__(self, api_key: str, model: str = "mayura:v1") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def backend_name(self) -> str:
        return f"Sarvam {self._model}"

    @property
    def supported_language_pairs(self) -> list[tuple[str, str]]:
        return self.SUPPORTED_PAIRS

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        session_id: str = "",
    ) -> NMTResult:
        payload = {
            "input": text,
            "source_language_code": source_language,
            "target_language_code": target_language,
            "model": self._model,
            "enable_preprocessing": True,
        }
        headers = {
            "Api-Subscription-Key": self._api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(SARVAM_TRANSLATE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return NMTResult(
            translated_text=data.get("translated_text", ""),
            source_language=source_language,
            target_language=target_language,
            model=self._model,
        )
