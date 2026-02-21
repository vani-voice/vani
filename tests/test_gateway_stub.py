"""
tests/test_gateway_stub.py — VaniGatewayStub pipeline tests (no API calls)
All backends are replaced with in-process stubs.
"""

import asyncio
import json
import pytest

from vani.backends.base import (
    CodeSwitchSpan,
    LLMResult,
    NMTResult,
    SynthesisResult,
    TranscriptResult,
    VamLLMBackend,
    VamSTTBackend,
    VamTTSBackend,
)
from vani.gateway.stub import GatewayEvent, TurnState, VaniGatewayStub
from vani.session import AudioCodec, SessionConfig


# ── Stub backends ────────────────────────────────────────────────────────────

class _StubSTT(VamSTTBackend):
    def __init__(self, transcripts: list[str]):
        self._transcripts = transcripts
        self._idx = 0

    @property
    def backend_name(self) -> str:
        return "stub-stt"

    @property
    def supported_languages(self) -> list[str]:
        return ["hi-IN", "ta-IN", "te-IN", "en"]

    async def transcribe_stream(self, audio_iter, language_hints, **kwargs):
        async for _ in audio_iter:
            pass
        text = self._transcripts[self._idx % len(self._transcripts)]
        self._idx += 1
        yield TranscriptResult(
            text=text, is_final=True, language_bcp47="hi-IN",
            utterance_id=f"utt-{self._idx}", confidence=0.95,
        )


class _StubLLM(VamLLMBackend):
    def __init__(self, response: str = "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?"):
        self._response = response

    @property
    def backend_name(self) -> str:
        return "stub-llm"

    @property
    def supported_languages(self) -> list[str]:
        return ["hi-IN", "en"]

    async def chat_stream(self, messages, tools=None, **kwargs):
        # Stream word by word
        words = self._response.split()
        for i, word in enumerate(words):
            is_final = i == len(words) - 1
            yield LLMResult(text_delta=word + (" " if not is_final else ""), is_final=is_final)


class _StubLLMWithToolCall(VamLLMBackend):
    """LLM that emits one tool call then a final text response."""

    @property
    def backend_name(self) -> str:
        return "stub-llm-tool"

    @property
    def supported_languages(self) -> list[str]:
        return ["hi-IN", "ta-IN"]

    async def chat_stream(self, messages, tools=None, **kwargs):
        # If history has a tool result, return a text response
        if any(m.get("role") == "tool" for m in messages):
            yield LLMResult(text_delta="விலை கிடைத்தது.", is_final=True, finish_reason="stop")
            return
        # Otherwise emit a tool call
        yield LLMResult(
            text_delta="",
            is_final=True,
            tool_call={"name": "enam_mandi_price", "arguments": {"crop": "tomato", "mandi": "Koyambedu"}},
            finish_reason="tool_calls",
        )


class _StubTTS(VamTTSBackend):
    @property
    def backend_name(self) -> str:
        return "stub-tts"

    @property
    def supported_languages(self) -> list[str]:
        return ["hi-IN", "ta-IN", "en"]

    async def synthesize_stream(self, text, language_bcp47, **kwargs):
        # One 40ms chunk of silence
        yield SynthesisResult(
            audio_bytes=b"\x00" * 1280,
            codec=AudioCodec.PCM_16K_16,
            is_final=True,
            duration_ms=40,
            chunk_index=0,
        )


async def _audio_gen(n: int = 5):
    for _ in range(n):
        yield b"\x00" * 640
        await asyncio.sleep(0)


# ── Tests: basic pipeline ────────────────────────────────────────────────────

class TestGatewayPipeline:
    @pytest.fixture
    def gateway(self):
        config = SessionConfig.for_hinglish(caller_id="+91-1234567890")
        return VaniGatewayStub(
            config=config,
            stt=_StubSTT(["नमस्ते, मुझे help चाहिए"]),
            llm=_StubLLM(),
            tts=_StubTTS(),
            system_prompt="You are a helpful assistant.",
        )

    @pytest.mark.asyncio
    async def test_turn_produces_events(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_transcript_event_emitted(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        final_transcripts = [e for e in events if e.transcript and e.transcript.is_final]
        assert len(final_transcripts) == 1
        assert final_transcripts[0].transcript.text == "नमस्ते, मुझे help चाहिए"

    @pytest.mark.asyncio
    async def test_turn_signals_include_listening(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        signals = [e.turn_signal.event for e in events if e.turn_signal]
        assert TurnState.LISTENING in signals

    @pytest.mark.asyncio
    async def test_turn_signals_include_thinking(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        signals = [e.turn_signal.event for e in events if e.turn_signal]
        assert TurnState.THINKING in signals

    @pytest.mark.asyncio
    async def test_synthesis_chunk_emitted(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        synth = [e for e in events if e.synthesis_chunk and e.synthesis_chunk.is_final]
        assert len(synth) >= 1
        assert synth[0].synthesis_chunk.audio_bytes == b"\x00" * 1280

    @pytest.mark.asyncio
    async def test_end_of_turn_emitted(self, gateway):
        events = [e async for e in gateway.process_audio(_audio_gen())]
        signals = [e.turn_signal.event for e in events if e.turn_signal]
        assert TurnState.END_OF_TURN in signals


# ── Tests: multi-turn history ────────────────────────────────────────────────

class TestMultiTurn:
    @pytest.fixture
    def gateway(self):
        config = SessionConfig.for_hinglish(caller_id="+91-0000000000")
        return VaniGatewayStub(
            config=config,
            stt=_StubSTT(["पहला सवाल", "दूसरा सवाल"]),
            llm=_StubLLM("ठीक है।"),
            tts=_StubTTS(),
            system_prompt="You are helpful.",
        )

    @pytest.mark.asyncio
    async def test_history_grows_across_turns(self, gateway):
        await gateway.process_audio(_audio_gen()).__anext__()
        # Drain turn 1
        async for _ in gateway.process_audio(_audio_gen()):
            pass
        history_len = len(gateway._history)
        # Each turn adds user + assistant messages
        assert history_len >= 2

    @pytest.mark.asyncio
    async def test_reset_clears_history(self, gateway):
        async for _ in gateway.process_audio(_audio_gen()):
            pass
        gateway.reset()
        # reset() keeps only the system prompt entry
        assert len(gateway._history) == 1
        assert gateway._history[0]["role"] == "system"


# ── Tests: action callback ───────────────────────────────────────────────────

class TestActionCallback:
    @pytest.mark.asyncio
    async def test_action_callback_fired(self):
        fired = {}

        async def callback(tool_name: str, args: dict) -> str:
            fired["tool"] = tool_name
            fired["args"] = args
            return json.dumps({"price": 1000})

        config = SessionConfig.for_language("ta-IN")
        gateway = VaniGatewayStub(
            config=config,
            stt=_StubSTT(["தக்காளி விலை என்ன?"]),
            llm=_StubLLMWithToolCall(),
            tts=_StubTTS(),
            system_prompt="You are a farming assistant.",
            action_callback=callback,
        )

        async for _ in gateway.process_audio(_audio_gen()):
            pass

        assert fired.get("tool") == "enam_mandi_price"
        assert fired["args"]["crop"] == "tomato"


# ── Tests: code-switch in transcript ─────────────────────────────────────────

class TestCodeSwitchTranscript:
    @pytest.mark.asyncio
    async def test_code_switch_spans_propagated(self):
        class _SpanSTT(VamSTTBackend):
            @property
            def backend_name(self):
                return "span-stt"

            @property
            def supported_languages(self):
                return ["hi-IN"]

            async def transcribe_stream(self, audio_iter, language_hints, **kwargs):
                async for _ in audio_iter:
                    pass
                yield TranscriptResult(
                    text="मुझे ये laptop बहुत पसंद है",
                    is_final=True,
                    language_bcp47="hi-IN",
                    code_switch_spans=[
                        CodeSwitchSpan(start_char=8, end_char=14, language_bcp47="en", confidence=0.94)
                    ],
                )

        config = SessionConfig.for_hinglish(caller_id="+91-9999999999")
        gateway = VaniGatewayStub(
            config=config,
            stt=_SpanSTT(),
            llm=_StubLLM(),
            tts=_StubTTS(),
            system_prompt="helpful",
        )
        events = [e async for e in gateway.process_audio(_audio_gen())]
        final = next(e for e in events if e.transcript and e.transcript.is_final)
        assert len(final.transcript.code_switch_spans) == 1
        span = final.transcript.code_switch_spans[0]
        assert span.start_char == 8
        assert span.end_char == 14
        assert final.transcript.text[span.start_char:span.end_char] == "laptop"
