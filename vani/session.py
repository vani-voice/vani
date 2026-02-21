"""
VaniSession — high-level session configuration object.

This module maps Python-native types onto the SessionInitRequest Protobuf
message, so callers never need to interact with Protobuf directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # generated Protobuf stubs imported lazily to avoid hard grpcio dep


# ─────────────────────────────────────────────────────────────────────────────
# Mirror enums from session.proto (kept in sync by hand until code-gen)
# ─────────────────────────────────────────────────────────────────────────────


class ModelBackend(str, Enum):
    """Supported STT/LLM/TTS model backend providers."""

    SARVAM = "SARVAM"
    AI4BHARAT = "AI4BHARAT"
    BHASHINI = "BHASHINI"
    AZURE = "AZURE"
    GOOGLE = "GOOGLE"
    CUSTOM = "CUSTOM"


class ScriptPreference(str, Enum):
    """Script for ASR transcript output."""

    NATIVE = "NATIVE"
    ROMAN = "ROMAN"
    BOTH = "BOTH"


class AudioCodec(str, Enum):
    """Audio codec for the session."""

    AMR_NB_8K = "AMR_NB_8K"    # Tier A — 2G
    OPUS_16K = "OPUS_16K"       # Tier B — 3G
    PCM_16K_16 = "PCM_16K_16"   # Tier C — 4G+


class DataResidency(str, Enum):
    """Audio and transcript data residency constraint."""

    INDIA_ONLY = "INDIA_ONLY"   # Recommended default; required for DPDP compliance
    ANY = "ANY"
    ON_PREM = "ON_PREM"         # Air-gapped, no outbound calls


# ─────────────────────────────────────────────────────────────────────────────
# Language helpers
# ─────────────────────────────────────────────────────────────────────────────

# Tier 1: ~65% of India's population; all have production-ready models
TIER1_LANGUAGES = ["hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN"]

# Tier 2: adds 5 more major languages
TIER2_LANGUAGES = ["kn-IN", "ml-IN", "gu-IN", "pa-IN", "or-IN"]

# Common code-switch pairs — supply BOTH hints for auto-detection
HINGLISH = [("hi-IN", 0.7), ("en-US", 0.3)]
TANGLISH = [("ta-IN", 0.7), ("en-US", 0.3)]
TENGLISH = [("te-IN", 0.7), ("en-US", 0.3)]
BANGLISH = [("bn-IN", 0.7), ("en-US", 0.3)]
MARATHLISH = [("mr-IN", 0.7), ("en-US", 0.3)]


@dataclass
class LanguageHint:
    """A language the caller expects to speak, with an optional confidence weight."""

    bcp47_code: str
    confidence: float = 0.0  # 0.0 = equal weight / auto

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")


@dataclass
class AudioProfile:
    """Audio codec configuration for the session."""

    codec: AudioCodec = AudioCodec.PCM_16K_16
    sample_rate: int = 16000
    channels: int = 1
    bitrate_kbps: int = 256  # Informational for Opus; ignored for PCM/AMR

    @classmethod
    def tier_a(cls) -> "AudioProfile":
        """2G/EDGE profile (AMR-NB 8kHz)."""
        return cls(codec=AudioCodec.AMR_NB_8K, sample_rate=8000, bitrate_kbps=12)

    @classmethod
    def tier_b(cls) -> "AudioProfile":
        """3G/HSPA profile (Opus 16kHz)."""
        return cls(codec=AudioCodec.OPUS_16K, sample_rate=16000, bitrate_kbps=32)

    @classmethod
    def tier_c(cls) -> "AudioProfile":
        """4G+/LAN profile (PCM 16kHz/16-bit)."""
        return cls(codec=AudioCodec.PCM_16K_16, sample_rate=16000, bitrate_kbps=256)


@dataclass
class ModelPreferences:
    """Ordered backend preferences per pipeline stage."""

    asr: list[ModelBackend] = field(
        default_factory=lambda: [ModelBackend.SARVAM, ModelBackend.AI4BHARAT, ModelBackend.BHASHINI]
    )
    llm: list[ModelBackend] = field(
        default_factory=lambda: [ModelBackend.SARVAM, ModelBackend.AI4BHARAT]
    )
    tts: list[ModelBackend] = field(
        default_factory=lambda: [ModelBackend.SARVAM, ModelBackend.AI4BHARAT, ModelBackend.BHASHINI]
    )
    nmt: list[ModelBackend] = field(
        default_factory=lambda: [ModelBackend.AI4BHARAT, ModelBackend.BHASHINI]
    )
    custom_backend_uri: str = ""  # Used when ModelBackend.CUSTOM is in any list


@dataclass
class SessionCapabilities:
    """Feature flags requested from the gateway."""

    code_switch_detection: bool = True
    dialect_routing: bool = False
    speaker_diarization: bool = False
    action_execution: bool = True
    transliteration_output: bool = False
    continuous_vad: bool = True
    noise_suppression: bool = False
    streaming_tts: bool = True


@dataclass
class SessionConfig:
    """
    Full configuration for a Vani session.

    This is the primary entry point for developers. Build a SessionConfig,
    pass it to VaniSession, and call ``session.start()`` to open the stream.

    Examples::

        from vani import SessionConfig, LanguageHint, HINGLISH

        # Hinglish customer support session — Tier C (4G, call center):
        config = SessionConfig.for_hinglish(caller_id="+91-9876543210")

        # Tamil voice agent — Tier B (3G rural):
        config = SessionConfig(
            language_hints=[LanguageHint("ta-IN")],
            audio_profile=AudioProfile.tier_b(),
            caller_id="+91-44-12345678",
        )
    """

    language_hints: list[LanguageHint] = field(default_factory=list)
    script_preference: ScriptPreference = ScriptPreference.NATIVE
    audio_profile: AudioProfile = field(default_factory=AudioProfile.tier_c)
    model_preferences: ModelPreferences = field(default_factory=ModelPreferences)
    data_residency: DataResidency = DataResidency.INDIA_ONLY
    capabilities: SessionCapabilities = field(default_factory=SessionCapabilities)
    caller_id: str = ""
    auth_token: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    # Auto-generated unique ID; override only in tests
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # ── Convenience constructors ─────────────────────────────────────────────

    @classmethod
    def for_hinglish(cls, caller_id: str = "", **kwargs: object) -> "SessionConfig":
        """Pre-configured for Hindi+English code-switching."""
        return cls(
            language_hints=[LanguageHint("hi-IN", 0.7), LanguageHint("en-US", 0.3)],
            caller_id=caller_id,
            capabilities=SessionCapabilities(code_switch_detection=True),
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def for_tanglish(cls, caller_id: str = "", **kwargs: object) -> "SessionConfig":
        """Pre-configured for Tamil+English code-switching."""
        return cls(
            language_hints=[LanguageHint("ta-IN", 0.7), LanguageHint("en-US", 0.3)],
            caller_id=caller_id,
            capabilities=SessionCapabilities(code_switch_detection=True),
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def for_language(cls, bcp47: str, caller_id: str = "", **kwargs: object) -> "SessionConfig":
        """Pre-configured for a single Indian language (no code-switching)."""
        return cls(
            language_hints=[LanguageHint(bcp47, 1.0)],
            caller_id=caller_id,
            capabilities=SessionCapabilities(code_switch_detection=False),
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def for_rural(cls, bcp47: str, caller_id: str = "", **kwargs: object) -> "SessionConfig":
        """Tier A profile for 2G rural deployments."""
        return cls(
            language_hints=[LanguageHint(bcp47, 1.0)],
            audio_profile=AudioProfile.tier_a(),
            caller_id=caller_id,
            capabilities=SessionCapabilities(
                code_switch_detection=False,
                streaming_tts=False,  # Batch TTS for Tier A
                continuous_vad=True,
            ),
            **kwargs,  # type: ignore[arg-type]
        )


class VaniSession:
    """
    A Vani agent session.

    This is the main object developers interact with. It holds the
    SessionConfig and manages the lifecycle of the gRPC stream.

    Note: In the v0.1 alpha, this class provides the session model and
    configuration. The actual gRPC transport is wired in the gateway stub
    (``VaniGatewayStub``). Full streaming I/O is exposed in the next release.
    """

    def __init__(self, config: SessionConfig) -> None:
        self.config = config
        self._active = False

    @property
    def session_id(self) -> str:
        return self.config.session_id

    @property
    def is_active(self) -> bool:
        return self._active

    def __repr__(self) -> str:
        langs = [h.bcp47_code for h in self.config.language_hints]
        return (
            f"VaniSession(id={self.session_id[:8]}..., "
            f"languages={langs}, "
            f"codec={self.config.audio_profile.codec.value}, "
            f"active={self._active})"
        )
