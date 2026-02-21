# vani/backends/__init__.py
from vani.backends.base import (
    VamSTTBackend,
    VamTTSBackend,
    VamLLMBackend,
    VamNMTBackend,
    TranscriptResult,
    SynthesisResult,
    LLMResult,
    NMTResult,
    CodeSwitchSpan,
)

__all__ = [
    "VamSTTBackend",
    "VamTTSBackend",
    "VamLLMBackend",
    "VamNMTBackend",
    "TranscriptResult",
    "SynthesisResult",
    "LLMResult",
    "NMTResult",
    "CodeSwitchSpan",
]
