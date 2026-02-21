"""
tests/test_proto_stubs.py — Generated proto stub sanity checks
"""

import pytest
from google.protobuf import descriptor


class TestSessionProto:
    def setup_method(self):
        from vani.generated.vani.v1 import session_pb2
        self.pb2 = session_pb2

    def test_package(self):
        assert self.pb2.DESCRIPTOR.package == "vani.v1"

    def test_session_init_request_fields(self):
        msg = self.pb2.SessionInitRequest()
        assert hasattr(msg, "session_id")
        assert hasattr(msg, "caller_id")
        assert hasattr(msg, "language_hints")

    def test_session_init_response_fields(self):
        msg = self.pb2.SessionInitResponse()
        assert hasattr(msg, "session_id")
        assert hasattr(msg, "status")

    def test_audio_codec_enum_pcm(self):
        assert self.pb2.AUDIO_CODEC_PCM_16K_16 is not None

    def test_audio_codec_enum_amr(self):
        assert self.pb2.AUDIO_CODEC_AMR_NB_8K is not None

    def test_audio_codec_enum_opus(self):
        assert self.pb2.AUDIO_CODEC_OPUS_16K is not None

    def test_model_backend_sarvam(self):
        assert self.pb2.MODEL_BACKEND_SARVAM is not None

    def test_model_backend_ai4bharat(self):
        assert self.pb2.MODEL_BACKEND_AI4BHARAT is not None

    def test_model_backend_bhashini(self):
        assert self.pb2.MODEL_BACKEND_BHASHINI is not None

    def test_data_residency_india_only(self):
        assert self.pb2.DATA_RESIDENCY_INDIA_ONLY is not None

    def test_session_end_notice_fields(self):
        msg = self.pb2.SessionEndNotice()
        assert hasattr(msg, "session_id")
        assert hasattr(msg, "reason")


class TestStreamProto:
    def setup_method(self):
        from vani.generated.vani.v1 import stream_pb2
        self.pb2 = stream_pb2

    def test_package(self):
        assert self.pb2.DESCRIPTOR.package == "vani.v1"

    def test_audio_chunk_fields(self):
        chunk = self.pb2.AudioChunk()
        assert hasattr(chunk, "audio_bytes")
        assert hasattr(chunk, "codec")
        assert hasattr(chunk, "offset_ms")

    def test_transcript_event_fields(self):
        t = self.pb2.TranscriptEvent()
        assert hasattr(t, "text")
        assert hasattr(t, "text_roman")
        assert hasattr(t, "detected_language_bcp47")
        assert hasattr(t, "code_switch_spans")

    def test_code_switch_span_fields(self):
        span = self.pb2.CodeSwitchSpan()
        assert hasattr(span, "start_char")
        assert hasattr(span, "end_char")
        assert hasattr(span, "language_bcp47")
        assert hasattr(span, "confidence")

    def test_turn_signal_fields(self):
        ts = self.pb2.TurnSignal()
        assert hasattr(ts, "event")
        assert hasattr(ts, "turn_id")

    def test_turn_event_listening(self):
        assert self.pb2.TURN_EVENT_LISTENING is not None

    def test_turn_event_thinking(self):
        assert self.pb2.TURN_EVENT_THINKING is not None

    def test_turn_event_speaking(self):
        assert self.pb2.TURN_EVENT_SPEAKING is not None

    def test_client_stream_message_oneofs(self):
        msg = self.pb2.ClientStreamMessage()
        assert msg.HasField("audio_chunk") is False  # default unset

    def test_gateway_stream_message_oneofs(self):
        msg = self.pb2.GatewayStreamMessage()
        # default is unset — WhichOneof returns None
        assert msg.WhichOneof("payload") is None

    def test_synthesis_request_fields(self):
        sr = self.pb2.SynthesisRequest()
        assert hasattr(sr, "text")
        assert hasattr(sr, "language_bcp47")

    def test_word_timing_fields(self):
        wt = self.pb2.WordTiming()
        assert hasattr(wt, "word")
        assert hasattr(wt, "start_ms")
        assert hasattr(wt, "end_ms")


class TestActionProto:
    def setup_method(self):
        from vani.generated.vani.v1 import action_pb2
        self.pb2 = action_pb2

    def test_package(self):
        assert self.pb2.DESCRIPTOR.package == "vani.v1"

    def test_mcp_tool_call_fields(self):
        call = self.pb2.McpToolCall()
        assert hasattr(call, "tool_name")
        assert hasattr(call, "arguments")

    def test_mcp_tool_result_fields(self):
        result = self.pb2.McpToolResult()
        assert hasattr(result, "is_error")
        assert hasattr(result, "content")

    def test_action_request_envelope_fields(self):
        env = self.pb2.ActionRequestEnvelope()
        assert hasattr(env, "session_id")
        assert hasattr(env, "call_id")
        assert hasattr(env, "turn_id")
        assert hasattr(env, "timeout_ms")

    def test_action_result_envelope_fields(self):
        env = self.pb2.ActionResultEnvelope()
        assert hasattr(env, "session_id")
        assert hasattr(env, "call_id")
        assert hasattr(env, "status")
        assert hasattr(env, "execution_ms")

    def test_action_status_enum_success(self):
        assert self.pb2.ACTION_STATUS_SUCCESS is not None

    def test_action_status_enum_policy_deny(self):
        assert self.pb2.ACTION_STATUS_POLICY_DENY is not None

    def test_action_source_llm(self):
        assert self.pb2.ACTION_SOURCE_LLM is not None

    def test_action_server_manifest_fields(self):
        m = self.pb2.ActionServerManifest()
        assert hasattr(m, "server_id")
        assert hasattr(m, "tools")
