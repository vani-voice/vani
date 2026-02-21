"""
tests/test_backends_base.py — Abstract backend contracts & result types
"""

import pytest

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
from vani.session import AudioCodec


# ── Result dataclasses ───────────────────────────────────────────────────────

class TestTranscriptResult:
    def test_required_fields(self):
        r = TranscriptResult(text="नमस्ते", is_final=True, language_bcp47="hi-IN")
        assert r.text == "नमस्ते"
        assert r.is_final is True
        assert r.language_bcp47 == "hi-IN"

    def test_optional_defaults_none(self):
        r = TranscriptResult(text="hello", is_final=False, language_bcp47="en")
        assert r.code_switch_spans is None or r.code_switch_spans == []
        assert r.dialect_tag is None or r.dialect_tag == ""

    def test_with_code_switch_spans(self):
        span = CodeSwitchSpan(start_char=8, end_char=14, language_bcp47="en", confidence=0.94)
        r = TranscriptResult(
            text="मुझे ये laptop बहुत पसंद है",
            is_final=True,
            language_bcp47="hi-IN",
            code_switch_spans=[span],
        )
        assert len(r.code_switch_spans) == 1
        assert r.code_switch_spans[0].start_char == 8
        assert r.code_switch_spans[0].end_char == 14


class TestCodeSwitchSpan:
    def test_fields(self):
        span = CodeSwitchSpan(start_char=0, end_char=5, language_bcp47="en", confidence=0.9)
        assert span.start_char == 0
        assert span.end_char == 5
        assert span.language_bcp47 == "en"
        assert span.confidence == pytest.approx(0.9)

    def test_unicode_offset_correctness(self):
        # "मुझे" = 4 Unicode code points (not bytes)
        text = "मुझे laptop"
        span = CodeSwitchSpan(start_char=5, end_char=11, language_bcp47="en", confidence=0.95)
        extracted = text[span.start_char:span.end_char]
        assert extracted == "laptop"

    def test_devanagari_offset_is_codepoint_not_byte(self):
        text = "मुझे ये laptop बहुत"
        # "मुझे " = 5 chars (4 Devanagari + space), " ये " = 4 chars
        # "laptop" starts at char 8
        span = CodeSwitchSpan(start_char=8, end_char=14, language_bcp47="en", confidence=0.9)
        assert text[span.start_char:span.end_char] == "laptop"
        # Verify UTF-8 bytes would give wrong answer
        encoded = text.encode("utf-8")
        # "मु" is 6 bytes, "झे" is 6 bytes — UTF-8 byte offset would be very different
        assert len("मुझे".encode("utf-8")) > len("मुझे")


class TestSynthesisResult:
    def test_fields(self):
        r = SynthesisResult(
            audio_bytes=b"\x00" * 1280,
            codec=AudioCodec.PCM_16K_16,
            is_final=False,
            duration_ms=40,
            chunk_index=0,
        )
        assert r.audio_bytes == b"\x00" * 1280
        assert r.codec == AudioCodec.PCM_16K_16
        assert r.duration_ms == 40
        assert r.chunk_index == 0


class TestLLMResult:
    def test_delta(self):
        r = LLMResult(text_delta="Hello", is_final=False)
        assert r.text_delta == "Hello"
        assert r.is_final is False

    def test_final(self):
        r = LLMResult(text_delta="", is_final=True, finish_reason="stop")
        assert r.is_final is True
        assert r.finish_reason == "stop"

    def test_tool_call_none_by_default(self):
        r = LLMResult(text_delta="Hi", is_final=False)
        assert r.tool_call is None


class TestNMTResult:
    def test_fields(self):
        r = NMTResult(
            translated_text="Hello",
            source_language="hi-IN",
            target_language="en",
            confidence=0.92,
            model="mayura:v1",
        )
        assert r.translated_text == "Hello"
        assert r.source_language == "hi-IN"
        assert r.confidence == pytest.approx(0.92)


# ── ABC enforcement ──────────────────────────────────────────────────────────

class TestAbstractBackends:
    def test_stt_backend_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            VamSTTBackend()  # type: ignore

    def test_tts_backend_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            VamTTSBackend()  # type: ignore

    def test_llm_backend_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            VamLLMBackend()  # type: ignore

    def test_nmt_backend_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            VamNMTBackend()  # type: ignore
