"""
Abstract base classes for Vani model backends.

All STT, TTS, LLM, and NMT provider integrations MUST subclass these ABCs
and implement the abstract methods. This ensures any backend is interchangeable
in the gateway pipeline.

Backend implementations live in:
  vani/backends/sarvam.py     — Sarvam AI (Saaras v3, Bulbul, Sarvam-M)
  vani/backends/ai4bharat.py  — AI4Bharat (IndicWhisper, AI4BTTS, Airavata)
  vani/backends/bhashini.py   — MeitY Bhashini / ULCA pipeline
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CodeSwitchSpan:
    """A code-switch annotation within a transcript segment."""

    start_char: int
    end_char: int
    language_bcp47: str
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    """
    The output of a STT backend for a single utterance segment.

    Mirrors TranscriptEvent in stream.proto.
    """

    text: str
    is_final: bool
    language_bcp47: str
    utterance_id: str = ""
    text_roman: str = ""           # Roman transliteration (if requested)
    detected_script: str = ""
    confidence: float = 0.0
    code_switch_spans: list[CodeSwitchSpan] = field(default_factory=list)
    dialect_tag: str = ""
    start_offset_ms: int = 0
    end_offset_ms: int = 0


@dataclass
class SynthesisResult:
    """
    A chunk of synthesized audio from a TTS backend.

    Mirrors SynthesisChunk in stream.proto.
    """

    audio_bytes: bytes
    codec: str                  # e.g. "PCM_16K_16", "OPUS_16K"
    is_final: bool = False
    duration_ms: int = 0
    chunk_index: int = 0


@dataclass
class LLMResult:
    """
    A single delta from an LLM backend in a streaming response.
    """

    text_delta: str
    is_final: bool = False
    tool_call: dict | None = None   # Populated when the LLM requests a tool
    finish_reason: str = ""         # "stop", "tool_calls", "length"


@dataclass
class NMTResult:
    """Output of a Neural Machine Translation backend."""

    translated_text: str
    source_language: str
    target_language: str
    confidence: float = 0.0
    model: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Abstract backend interfaces
# ─────────────────────────────────────────────────────────────────────────────


class VamSTTBackend(abc.ABC):
    """
    Abstract Automatic Speech Recognition backend.

    Implementations must handle streaming audio input and yield
    TranscriptResult objects — both partial and final — as the
    speaker's utterance is processed.

    Conformance requirement (VAM/1.0):
    - MUST yield at least one final TranscriptResult per utterance
    - MUST populate ``code_switch_spans`` when the session has
      ``code_switch_detection`` enabled
    - MUST populate ``dialect_tag`` when the session has
      ``dialect_routing`` enabled
    """

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend name, e.g. 'Sarvam Saaras v3'."""
        ...

    @property
    @abc.abstractmethod
    def supported_languages(self) -> list[str]:
        """BCP-47 codes this backend supports."""
        ...

    @property
    def supports_code_switching(self) -> bool:
        """Override to True in backends that natively handle code-switching."""
        return False

    @property
    def supports_streaming(self) -> bool:
        """Override to False in batch-only backends (e.g. Bhashini REST)."""
        return True

    @abc.abstractmethod
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
        Consume a stream of raw audio bytes and yield TranscriptResult objects.

        Args:
            audio_iter: Async iterator of audio byte chunks in the negotiated codec.
            language_hints: Ordered list of BCP-47 codes (e.g. ["hi-IN", "en-US"]).
            session_id: Vani session identifier for logging.
            code_switch: Whether to annotate CodeSwitchSpans in results.
            dialect_routing: Whether to populate dialect_tag in results.

        Yields:
            TranscriptResult — partial (is_final=False) or final (is_final=True).
        """
        ...

    async def health_check(self) -> bool:
        """Ping the backend to verify availability. Returns True if healthy."""
        return True


class VamTTSBackend(abc.ABC):
    """
    Abstract Text-to-Speech synthesis backend.

    Implementations must accept text and synthesis parameters and yield
    SynthesisResult audio chunks for streaming playback.
    """

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def supported_languages(self) -> list[str]:
        ...

    @property
    def supports_streaming(self) -> bool:
        """Return False for backends that only return full audio files."""
        return True

    @abc.abstractmethod
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
        Synthesize text to audio and yield SynthesisResult chunks.

        The last emitted chunk will have ``is_final = True``.
        """
        ...

    async def health_check(self) -> bool:
        return True


class VamLLMBackend(abc.ABC):
    """
    Abstract Large Language Model backend.

    Implementations must support streaming token generation and
    tool/function calling compatible with MCP tool call semantics.
    """

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def supported_languages(self) -> list[str]:
        """Languages this LLM has been tested/fine-tuned for."""
        ...

    @abc.abstractmethod
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
        """
        Stream a chat completion.

        Args:
            messages: OpenAI-compatible message list (role/content).
            tools: MCP tool schemas (JSON Schema format) for function calling.
            language_hint: Preferred response language BCP-47.
            session_id: For logging.
            max_tokens: Limits response length to control TTS latency.
            temperature: Sampling temperature.

        Yields:
            LLMResult — text deltas and/or tool call objects.
        """
        ...

    async def health_check(self) -> bool:
        return True


class VamNMTBackend(abc.ABC):
    """
    Abstract Neural Machine Translation backend.

    Used for inter-language relay (e.g. translate a Tamil query to Hindi
    before sending to a Hindi-optimized LLM).
    """

    @property
    @abc.abstractmethod
    def backend_name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def supported_language_pairs(self) -> list[tuple[str, str]]:
        """List of (source_bcp47, target_bcp47) pairs this backend supports."""
        ...

    @abc.abstractmethod
    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        session_id: str = "",
    ) -> NMTResult:
        ...

    async def health_check(self) -> bool:
        return True
