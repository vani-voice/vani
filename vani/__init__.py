"""
Vani — Vernacular Agent Middleware for Indian Languages
VAM/1.0 Reference Python SDK

वाणी (Vāṇī) — Sanskrit for "speech" or "voice"

Apache License 2.0 — Copyright 2026 Vani Protocol Authors
"""

from vani._version import __version__
from vani.session import VaniSession, SessionConfig
from vani.backends.base import (
    VamSTTBackend,
    VamTTSBackend,
    VamLLMBackend,
    VamNMTBackend,
    TranscriptResult,
    SynthesisResult,
    LLMResult,
)
from vani.gateway.stub import VaniGatewayStub

__all__ = [
    "__version__",
    "VaniSession",
    "SessionConfig",
    "VamSTTBackend",
    "VamTTSBackend",
    "VamLLMBackend",
    "VamNMTBackend",
    "TranscriptResult",
    "SynthesisResult",
    "LLMResult",
    "VaniGatewayStub",
]
