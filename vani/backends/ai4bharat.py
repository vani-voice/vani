"""
AI4Bharat backend implementation for Vani.

Implements VamSTTBackend using AI4Bharat's IndicWhisper models,
and VamNMTBackend using IndicTrans2.

These are fully open-source, self-hostable backends — no API key required.
Models are loaded from Hugging Face (ai4bharat/indic-whisper-large-v2, etc.)

Install: pip install vani[ai4bharat]

Note: IndicWhisper requires a GPU for production-latency inference.
For edge/on-prem Tier A deployments, use a quantized GGUF variant.
"""

from __future__ import annotations

import asyncio
import io
from typing import AsyncIterator

try:
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
except ImportError as e:
    raise ImportError(
        "AI4Bharat backend requires 'torch' and 'transformers'. "
        "Install with: pip install vani[ai4bharat]"
    ) from e

from vani.backends.base import (
    NMTResult,
    SynthesisResult,
    TranscriptResult,
    VamNMTBackend,
    VamSTTBackend,
    VamTTSBackend,
)

# AI4Bharat model identifiers on Hugging Face
INDIC_WHISPER_MODELS = {
    "large": "ai4bharat/indic-whisper-large-v2",
    "medium": "ai4bharat/indic-whisper-medium",
}

INDIC_TRANS2_MODEL = "ai4bharat/indictrans2-indic-en-dist-200M"

# Languages supported by IndicWhisper
INDIC_WHISPER_LANGUAGES = [
    "hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN",
    "kn-IN", "ml-IN", "gu-IN", "pa-IN", "or-IN",
    "as-IN", "ur-IN", "mai-IN",
]


class AI4BharatSTTBackend(VamSTTBackend):
    """
    AI4Bharat IndicWhisper STT backend.

    This backend runs locally using HuggingFace Transformers.
    For streaming simulation, audio is buffered until end-of-speech,
    then transcribed as a single batch (IndicWhisper does not have a
    native streaming WebSocket API; streaming is emulated).

    Args:
        model_size: "medium" (faster, ~500ms) or "large" (better WER, ~800ms–2s)
        device: "cuda", "mps", or "cpu"
        model_id: Override the HuggingFace model ID directly
    """

    def __init__(
        self,
        model_size: str = "medium",
        device: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._model_id = model_id or INDIC_WHISPER_MODELS.get(model_size, INDIC_WHISPER_MODELS["medium"])
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._pipe = None  # Lazy-loaded on first call

    def _load_model(self) -> None:
        """Lazy-load the Whisper model. Called on first transcription."""
        if self._pipe is not None:
            return

        torch_dtype = torch.float16 if self._device == "cuda" else torch.float32

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self._model_id,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
        model.to(self._device)

        processor = AutoProcessor.from_pretrained(self._model_id)

        self._pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=self._device,
        )

    @property
    def backend_name(self) -> str:
        return f"AI4Bharat IndicWhisper ({self._model_id.split('/')[-1]})"

    @property
    def supported_languages(self) -> list[str]:
        return INDIC_WHISPER_LANGUAGES

    @property
    def supports_streaming(self) -> bool:
        # IndicWhisper is batch-mode; streaming is emulated via VAD gating
        return False

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
        Buffer all audio chunks, then run IndicWhisper batch inference.

        Emits one partial "processing..." result immediately for UI feedback,
        followed by one final TranscriptResult.
        """
        import uuid

        utterance_id = str(uuid.uuid4())
        language_code = language_hints[0] if language_hints else "hi-IN"

        # Emit a partial immediately so TurnSignal(THINKING) can be shown
        yield TranscriptResult(
            text="",
            is_final=False,
            language_bcp47=language_code,
            utterance_id=utterance_id,
        )

        # Buffer audio
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

        # Run inference in a thread pool to avoid blocking the event loop
        self._load_model()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self._run_inference, audio_bytes, language_code
        )

        yield TranscriptResult(
            text=result.get("text", "").strip(),
            is_final=True,
            language_bcp47=language_code,
            utterance_id=utterance_id,
            confidence=0.85,  # IndicWhisper does not return per-utterance confidence
        )

    def _run_inference(self, audio_bytes: bytes, language_code: str) -> dict:
        """Run synchronous IndicWhisper inference (called in thread pool)."""
        import numpy as np
        import soundfile as sf

        # Decode audio bytes to numpy array
        audio_file = io.BytesIO(audio_bytes)
        try:
            audio_array, sample_rate = sf.read(audio_file, dtype="float32")
        except Exception:
            return {"text": ""}

        # Map BCP-47 to Whisper language code
        lang_map = {
            "hi-IN": "hindi", "ta-IN": "tamil", "te-IN": "telugu",
            "bn-IN": "bengali", "mr-IN": "marathi", "kn-IN": "kannada",
            "ml-IN": "malayalam", "gu-IN": "gujarati", "pa-IN": "punjabi",
            "or-IN": "odia", "as-IN": "assamese", "ur-IN": "urdu",
        }
        whisper_lang = lang_map.get(language_code, "hindi")

        return self._pipe(
            {"array": audio_array, "sampling_rate": sample_rate},
            generate_kwargs={"language": whisper_lang, "task": "transcribe"},
        )


# ─────────────────────────────────────────────────────────────────────────────


class AI4BharatNMTBackend(VamNMTBackend):
    """
    AI4Bharat IndicTrans2 Neural Machine Translation backend.

    Covers all 22 scheduled Indian languages.
    Apache 2.0 licensed — fully open-source and self-hostable.
    """

    def __init__(
        self,
        model_id: str = INDIC_TRANS2_MODEL,
        device: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._tokenizer = None

    @property
    def backend_name(self) -> str:
        return "AI4Bharat IndicTrans2"

    @property
    def supported_language_pairs(self) -> list[tuple[str, str]]:
        # IndicTrans2 supports all Indic↔Indic and Indic↔English pairs
        indic = [
            "hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN", "kn-IN", "ml-IN",
            "gu-IN", "pa-IN", "or-IN", "as-IN", "ur-IN", "mai-IN", "kok-IN",
            "sat-IN", "mni-IN", "doi-IN", "sd-IN", "ks-IN", "ne-IN",
        ]
        pairs = []
        for src in indic:
            for tgt in indic + ["en-IN"]:
                if src != tgt:
                    pairs.append((src, tgt))
        return pairs

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        *,
        session_id: str = "",
    ) -> NMTResult:
        """
        Translate text using IndicTrans2.
        Runs synchronous model inference in a thread pool.
        """
        loop = asyncio.get_event_loop()
        translated = await loop.run_in_executor(
            None, self._run_translation, text, source_language, target_language
        )
        return NMTResult(
            translated_text=translated,
            source_language=source_language,
            target_language=target_language,
            model=self._model_id.split("/")[-1],
        )

    def _run_translation(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Synchronous IndicTrans2 inference (runs in thread pool)."""
        if self._model is None:
            try:
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                self._tokenizer = AutoTokenizer.from_pretrained(
                    self._model_id, trust_remote_code=True
                )
                self._model = AutoModelForSeq2SeqLM.from_pretrained(
                    self._model_id, trust_remote_code=True
                ).to(self._device)
            except Exception as exc:
                return f"[TRANSLATION_ERROR: {exc}]"

        try:
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                padding=True,
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    num_beams=4,
                    max_length=256,
                )

            return self._tokenizer.decode(outputs[0], skip_special_tokens=True)
        except Exception as exc:
            return f"[TRANSLATION_ERROR: {exc}]"


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder TTS (AI4Bharat TTS quality lags Sarvam; included for completeness)
# ─────────────────────────────────────────────────────────────────────────────


class AI4BharatTTSBackend(VamTTSBackend):
    """
    AI4Bharat TTS backend (placeholder).

    AI4Bharat's open-source TTS (trained on the Rasa dataset) is available
    but trails Sarvam Bulbul in voice quality for conversational use.
    This stub documents the interface; a full implementation requires the
    AI4Bharat TTS inference server (see ai4bharat/indicTTS on GitHub).
    """

    @property
    def backend_name(self) -> str:
        return "AI4Bharat IndicTTS"

    @property
    def supported_languages(self) -> list[str]:
        return ["hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN", "kn-IN", "ml-IN", "gu-IN"]

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
        raise NotImplementedError(
            "AI4Bharat TTS full implementation is in progress. "
            "Use SarvamTTSBackend for production. "
            "Track: https://github.com/vani-protocol/vani/issues/XX"
        )
        # Satisfy the type checker for AsyncIterator protocol
        yield SynthesisResult(audio_bytes=b"", codec=output_codec, is_final=True)  # type: ignore[misc]
