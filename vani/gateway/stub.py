"""
VaniGatewayStub — reference no-op gateway implementation.

This stub implements the Vani Gateway interface using the abstract backends.
It serves three purposes:
1. Local development / unit testing without a live gRPC server
2. Demonstrating the gateway pipeline architecture
3. Conformance test target for the YAML-based test suite

In production, a real gateway would run this pipeline over gRPC with
VaniSessionService + VaniStreamService from the generated proto stubs.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable

import structlog

from vani.backends.base import (
    LLMResult,
    SynthesisResult,
    TranscriptResult,
    VamLLMBackend,
    VamSTTBackend,
    VamTTSBackend,
)
from vani.session import SessionConfig, SessionCapabilities

logger = structlog.get_logger("vani.gateway")


class TurnState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    END_OF_TURN = "END_OF_TURN"
    ERROR = "ERROR"


@dataclass
class TurnSignal:
    """Python mirror of stream.proto TurnSignal."""
    event: TurnState
    turn_id: str
    session_id: str
    elapsed_ms: int = 0


@dataclass
class GatewayEvent:
    """Union type for events emitted by the gateway pipeline."""

    transcript: TranscriptResult | None = None
    turn_signal: TurnSignal | None = None
    synthesis_chunk: SynthesisResult | None = None
    llm_text: str | None = None
    error: str | None = None


# Type alias for action callback: receives tool name + args dict, returns result string
ActionCallback = Callable[[str, dict], "asyncio.Future[str]"]


class VaniGatewayStub:
    """
    Reference Vani Gateway pipeline.

    Wires STT → LLM → TTS in sequence and emits GatewayEvents.
    Supports VAD-gated streaming, code-switch detection, and action callbacks.

    Usage::

        from vani import SessionConfig, VaniGatewayStub
        from vani.backends.sarvam import SarvamSTTBackend, SarvamTTSBackend, SarvamLLMBackend

        config = SessionConfig.for_hinglish(caller_id="demo")

        gateway = VaniGatewayStub(
            config=config,
            stt=SarvamSTTBackend(api_key="..."),
            llm=SarvamLLMBackend(api_key="..."),
            tts=SarvamTTSBackend(api_key="..."),
            system_prompt="You are a helpful customer support agent. Respond in the same language as the user.",
        )

        async for event in gateway.process_audio(audio_iter):
            if event.transcript and event.transcript.is_final:
                print("User said:", event.transcript.text)
            if event.synthesis_chunk and event.synthesis_chunk.is_final:
                print("[TTS complete]")
    """

    def __init__(
        self,
        config: SessionConfig,
        stt: VamSTTBackend,
        llm: VamLLMBackend,
        tts: VamTTSBackend,
        *,
        system_prompt: str = "You are a helpful voice assistant. Respond concisely.",
        action_callback: ActionCallback | None = None,
        max_history_turns: int = 10,
    ) -> None:
        self.config = config
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.system_prompt = system_prompt
        self.action_callback = action_callback
        self.max_history_turns = max_history_turns

        self._state = TurnState.IDLE
        self._turn_id = str(uuid.uuid4())
        self._history: list[dict] = [{"role": "system", "content": system_prompt}]
        self._log = logger.bind(session_id=config.session_id[:8])

    @property
    def state(self) -> TurnState:
        return self._state

    def _transition(self, new_state: TurnState) -> TurnSignal:
        self._state = new_state
        self._log.info("turn_transition", state=new_state.value)
        return TurnSignal(
            event=new_state,
            turn_id=self._turn_id,
            session_id=self.config.session_id,
        )

    async def process_audio(
        self,
        audio_iter: AsyncIterator[bytes],
    ) -> AsyncIterator[GatewayEvent]:
        """
        Process a full audio utterance through the STT→LLM→TTS pipeline.

        Yields GatewayEvents in order:
          TurnSignal(LISTENING) → TranscriptEvents → TurnSignal(THINKING)
          → TurnSignal(SPEAKING) → SynthesisChunks → TurnSignal(END_OF_TURN)

        Args:
            audio_iter: Async iterator of raw audio bytes for one utterance.
        """
        caps: SessionCapabilities = self.config.capabilities
        language_hints = [h.bcp47_code for h in self.config.language_hints]

        # ── LISTENING ────────────────────────────────────────────────────────
        yield GatewayEvent(turn_signal=self._transition(TurnState.LISTENING))

        final_transcript: TranscriptResult | None = None

        async for result in self.stt.transcribe_stream(
            audio_iter,
            language_hints,
            session_id=self.config.session_id,
            code_switch=caps.code_switch_detection,
            dialect_routing=caps.dialect_routing,
        ):
            yield GatewayEvent(transcript=result)
            if result.is_final:
                final_transcript = result

        if not final_transcript or not final_transcript.text.strip():
            yield GatewayEvent(turn_signal=self._transition(TurnState.IDLE))
            return

        # ── THINKING ─────────────────────────────────────────────────────────
        yield GatewayEvent(turn_signal=self._transition(TurnState.THINKING))

        # Build LLM message — pass both native and Roman if available
        user_content = final_transcript.text
        if final_transcript.text_roman:
            user_content += f"\n[Transliteration: {final_transcript.text_roman}]"
        if final_transcript.code_switch_spans:
            switch_info = ", ".join(
                f"'{user_content[s.start_char:s.end_char]}' ({s.language_bcp47})"
                for s in final_transcript.code_switch_spans
            )
            user_content += f"\n[Code-switch: {switch_info}]"

        self._history.append({"role": "user", "content": user_content})

        # Trim history to prevent context overflow
        if len(self._history) > self.max_history_turns * 2 + 1:
            self._history = [self._history[0]] + self._history[-(self.max_history_turns * 2):]

        # Determine response language
        response_lang = final_transcript.language_bcp47 or language_hints[0]

        # Collect full LLM response (handle tool calls if action_callback is set)
        full_response_text = ""
        async for llm_delta in self.llm.chat_stream(
            self._history,
            language_hint=response_lang,
            session_id=self.config.session_id,
        ):
            if llm_delta.tool_call and self.action_callback:
                # Execute action and inject result back into context
                tool_result = await self._execute_action(llm_delta.tool_call)
                self._history.append({
                    "role": "tool",
                    "content": tool_result,
                    "tool_call_id": llm_delta.tool_call.get("id", ""),
                })
            elif llm_delta.text_delta:
                full_response_text += llm_delta.text_delta

        if not full_response_text.strip():
            yield GatewayEvent(turn_signal=self._transition(TurnState.IDLE))
            return

        self._history.append({"role": "assistant", "content": full_response_text})

        # Emit LLM text so clients can display the assistant's response
        yield GatewayEvent(llm_text=full_response_text)

        # ── SPEAKING ─────────────────────────────────────────────────────────
        yield GatewayEvent(turn_signal=self._transition(TurnState.SPEAKING))

        async for chunk in self.tts.synthesize_stream(
            full_response_text,
            response_lang,
            output_codec=self.config.audio_profile.codec.value,
            session_id=self.config.session_id,
        ):
            yield GatewayEvent(synthesis_chunk=chunk)

        # ── END_OF_TURN ───────────────────────────────────────────────────────
        self._turn_id = str(uuid.uuid4())  # New turn ID for next interaction
        yield GatewayEvent(turn_signal=self._transition(TurnState.END_OF_TURN))

        # Reset to IDLE for next utterance
        self._transition(TurnState.IDLE)

    async def _execute_action(self, tool_call: dict) -> str:
        """Dispatch a tool call to the registered action callback."""
        if self.action_callback is None:
            return '{"error": "No action callback registered"}'

        tool_name = (
            tool_call.get("function", {}).get("name")
            or tool_call.get("name", "unknown_tool")
        )
        import json

        try:
            args_raw = (
                tool_call.get("function", {}).get("arguments")
                or tool_call.get("arguments")
                or tool_call.get("input")
                or "{}"
            )
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}

        try:
            result = await self.action_callback(tool_name, args)
            return result
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def reset(self) -> None:
        """Reset conversation history (keep system prompt)."""
        self._history = [{"role": "system", "content": self.system_prompt}]
        self._state = TurnState.IDLE
        self._turn_id = str(uuid.uuid4())
        self._log.info("session_reset")

    def __repr__(self) -> str:
        return (
            f"VaniGatewayStub("
            f"session={self.config.session_id[:8]}..., "
            f"state={self._state.value}, "
            f"stt={self.stt.backend_name}, "
            f"llm={self.llm.backend_name}, "
            f"tts={self.tts.backend_name})"
        )
