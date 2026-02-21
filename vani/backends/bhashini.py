"""
Bhashini / ULCA backend implementation for Vani.

Implements VamSTTBackend, VamTTSBackend, and VamNMTBackend using
MeitY's Bhashini ULCA (Unified Language Contribution API) pipeline.

Bhashini is India's National Language Translation Mission and provides
coverage for all 36+ supported languages, including low-resource ones.

Limitations:
- The public ULCA API is REST-based (not streaming) → Tier A / batch mode only
- Requires a ULCA API key from https://bhashini.gov.in/ulca
- SLA is not publicly guaranteed; treat as supplemental fallback

Install: pip install vani[bhashini]
"""

from __future__ import annotations

import io
from typing import AsyncIterator

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "Bhashini backend requires 'httpx'. "
        "Install with: pip install vani[bhashini]"
    ) from e

from vani.backends.base import (
    NMTResult,
    SynthesisResult,
    TranscriptResult,
    VamNMTBackend,
    VamSTTBackend,
    VamTTSBackend,
)

# Bhashini ULCA inference endpoint
ULCA_BASE = "https://meity-ai.ulcacontrib.org/ulca/apis/v0/model/compute"

# Bhashini-supported language codes (BCP-47 → Bhashini internal code)
BHASHINI_LANG_MAP: dict[str, str] = {
    "hi-IN": "hi",
    "ta-IN": "ta",
    "te-IN": "te",
    "bn-IN": "bn",
    "mr-IN": "mr",
    "kn-IN": "kn",
    "ml-IN": "ml",
    "gu-IN": "gu",
    "pa-IN": "pa",
    "or-IN": "or",
    "as-IN": "as",
    "ur-IN": "ur",
    "mai-IN": "mai",
    "kok-IN": "kok",
    "sat-IN": "sat",
    "mni-IN": "mni",
    "doi-IN": "doi",
    "sd-IN": "sd",
    "ks-IN": "ks",
    "ne-IN": "ne",
    "en-IN": "en",
}


class BhashiniSTTBackend(VamSTTBackend):
    """
    Bhashini ULCA ASR backend (REST batch mode).

    Because the ULCA API is request-response (not a streaming WebSocket),
    this backend operates in Tier A / batch mode: it buffers the full
    audio, sends it to ULCA, and returns a single final TranscriptResult.

    Supports all 22 scheduled Indian languages — valuable for low-resource
    languages (Santali `sat-IN`, Manipuri `mni-IN`) not available elsewhere.
    """

    def __init__(
        self,
        user_id: str,
        ulca_api_key: str,
        pipeline_id: str = "64392f96daac500b55c543cd",  # Bhashini default ASR pipeline
    ) -> None:
        self._user_id = user_id
        self._api_key = ulca_api_key
        self._pipeline_id = pipeline_id

    @property
    def backend_name(self) -> str:
        return "Bhashini ULCA ASR"

    @property
    def supported_languages(self) -> list[str]:
        return list(BHASHINI_LANG_MAP.keys())

    @property
    def supports_streaming(self) -> bool:
        return False  # ULCA is batch-only

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
        Buffer audio, then POST to Bhashini ULCA ASR pipeline.
        Emits one final TranscriptResult.
        """
        import base64
        import uuid

        utterance_id = str(uuid.uuid4())
        language_code = language_hints[0] if language_hints else "hi-IN"
        bhashini_lang = BHASHINI_LANG_MAP.get(language_code, "hi")

        # Buffer all audio
        buffer = io.BytesIO()
        async for chunk in audio_iter:
            buffer.write(chunk)
        audio_bytes = buffer.getvalue()

        if not audio_bytes:
            yield TranscriptResult(
                text="",
                is_final=True,
                language_bcp47=language_code,
                utterance_id=utterance_id,
            )
            return

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": bhashini_lang},
                        "serviceId": "",
                        "audioFormat": "wav",
                        "samplingRate": 16000,
                        "encoding": "base64",
                        "channel": "1",
                    },
                }
            ],
            "inputData": {
                "audio": [{"audioContent": audio_b64}]
            },
        }

        headers = {
            "userId": self._user_id,
            "ulcaApiKey": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(ULCA_BASE, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            transcript_text = (
                data.get("pipelineResponse", [{}])[0]
                .get("output", [{}])[0]
                .get("source", "")
            )
        except Exception as exc:
            transcript_text = f"[BHASHINI_ERROR: {exc}]"

        yield TranscriptResult(
            text=transcript_text.strip(),
            is_final=True,
            language_bcp47=language_code,
            utterance_id=utterance_id,
        )


class BhashiniTTSBackend(VamTTSBackend):
    """
    Bhashini ULCA TTS backend (REST batch mode).

    Returns audio as a single payload after synthesis — no streaming.
    Chunked into frames before yielding for gateway compatibility.
    """

    def __init__(
        self,
        user_id: str,
        ulca_api_key: str,
        pipeline_id: str = "64392f96daac500b55c543cd",
    ) -> None:
        self._user_id = user_id
        self._api_key = ulca_api_key
        self._pipeline_id = pipeline_id

    @property
    def backend_name(self) -> str:
        return "Bhashini ULCA TTS"

    @property
    def supported_languages(self) -> list[str]:
        return list(BHASHINI_LANG_MAP.keys())

    @property
    def supports_streaming(self) -> bool:
        return False

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
        import base64

        bhashini_lang = BHASHINI_LANG_MAP.get(language_bcp47, "hi")
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": bhashini_lang},
                        "serviceId": "",
                        "gender": "female",
                        "samplingRate": 16000,
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
        }

        headers = {
            "userId": self._user_id,
            "ulcaApiKey": self._api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(ULCA_BASE, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        audio_b64 = (
            data.get("pipelineResponse", [{}])[0]
            .get("audio", [{}])[0]
            .get("audioContent", "")
        )
        audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

        # Chunk into frames
        chunk_size = 1280
        total = len(audio_bytes)
        for i, offset in enumerate(range(0, max(total, 1), chunk_size)):
            chunk = audio_bytes[offset : offset + chunk_size]
            is_final = (offset + chunk_size) >= total
            yield SynthesisResult(
                audio_bytes=chunk,
                codec=output_codec,
                is_final=is_final,
                duration_ms=40,
                chunk_index=i,
            )


class BhashiniNMTBackend(VamNMTBackend):
    """
    Bhashini ULCA NMT backend.

    Covers translation between all 22 scheduled Indian languages.
    """

    def __init__(self, user_id: str, ulca_api_key: str) -> None:
        self._user_id = user_id
        self._api_key = ulca_api_key

    @property
    def backend_name(self) -> str:
        return "Bhashini ULCA NMT"

    @property
    def supported_language_pairs(self) -> list[tuple[str, str]]:
        langs = list(BHASHINI_LANG_MAP.keys())
        return [(s, t) for s in langs for t in langs if s != t]

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        session_id: str = "",
    ) -> NMTResult:
        src = BHASHINI_LANG_MAP.get(source_language, "hi")
        tgt = BHASHINI_LANG_MAP.get(target_language, "en")

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": src,
                            "targetLanguage": tgt,
                        },
                        "serviceId": "",
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
        }

        headers = {
            "userId": self._user_id,
            "ulcaApiKey": self._api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(ULCA_BASE, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        translated = (
            data.get("pipelineResponse", [{}])[0]
            .get("output", [{}])[0]
            .get("target", "")
        )

        return NMTResult(
            translated_text=translated,
            source_language=source_language,
            target_language=target_language,
            model="Bhashini ULCA NMT",
        )
