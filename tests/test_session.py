"""
tests/test_session.py — Session config & negotiation tests
"""

import pytest

from vani.session import (
    AudioCodec,
    AudioProfile,
    DataResidency,
    LanguageHint,
    ModelBackend,
    ModelPreferences,
    ScriptPreference,
    SessionCapabilities,
    SessionConfig,
    TIER1_LANGUAGES,
    HINGLISH,
    TANGLISH,
    TENGLISH,
    BANGLISH,
    MARATHLISH,
)


# ── SessionConfig convenience constructors ──────────────────────────────────

class TestSessionConfigConstructors:
    def test_for_hinglish_language(self):
        c = SessionConfig.for_hinglish(caller_id="+91-9876543210")
        assert c.language_hints[0].bcp47_code == "hi-IN"
        assert any(h.bcp47_code in ("en", "en-US") for h in c.language_hints)

    def test_for_hinglish_codec(self):
        c = SessionConfig.for_hinglish(caller_id="+91-9876543210")
        assert c.audio_profile.codec == AudioCodec.PCM_16K_16

    def test_for_hinglish_has_session_id(self):
        c = SessionConfig.for_hinglish(caller_id="+91-9876543210")
        assert c.session_id and len(c.session_id) > 8

    def test_for_hinglish_code_switch_capability(self):
        c = SessionConfig.for_hinglish(caller_id="+91-9876543210")
        assert c.capabilities.code_switch_detection is True

    def test_for_tanglish(self):
        c = SessionConfig.for_tanglish(caller_id="+91-9876543210")
        assert c.language_hints[0].bcp47_code == "ta-IN"

    def test_for_tenglish(self):
        c = SessionConfig.for_language("te-IN")
        assert c.language_hints[0].bcp47_code == "te-IN"

    def test_for_rural_uses_tier_a(self):
        c = SessionConfig.for_rural("hi-IN")
        assert c.audio_profile.codec == AudioCodec.AMR_NB_8K

    def test_for_language_with_tier_b(self):
        c = SessionConfig.for_language("ta-IN", audio_profile=AudioProfile.tier_b())
        assert c.audio_profile.codec == AudioCodec.OPUS_16K

    def test_different_callers_get_different_session_ids(self):
        c1 = SessionConfig.for_hinglish(caller_id="+91-1111111111")
        c2 = SessionConfig.for_hinglish(caller_id="+91-2222222222")
        assert c1.session_id != c2.session_id

    def test_data_residency_defaults_to_india(self):
        c = SessionConfig.for_hinglish(caller_id="+91-9876543210")
        assert c.data_residency == DataResidency.INDIA_ONLY


# ── AudioProfile tiers ───────────────────────────────────────────────────────

class TestAudioProfile:
    def test_tier_a_codec(self):
        p = AudioProfile.tier_a()
        assert p.codec == AudioCodec.AMR_NB_8K

    def test_tier_b_codec(self):
        p = AudioProfile.tier_b()
        assert p.codec == AudioCodec.OPUS_16K

    def test_tier_c_codec(self):
        p = AudioProfile.tier_c()
        assert p.codec == AudioCodec.PCM_16K_16

    def test_tier_a_sample_rate(self):
        p = AudioProfile.tier_a()
        assert p.sample_rate == 8000

    def test_tier_b_sample_rate(self):
        p = AudioProfile.tier_b()
        assert p.sample_rate == 16000

    def test_tier_c_sample_rate(self):
        p = AudioProfile.tier_c()
        assert p.sample_rate == 16000


# ── Constants ────────────────────────────────────────────────────────────────

class TestConstants:
    def test_tier1_languages_count(self):
        assert len(TIER1_LANGUAGES) >= 5

    def test_tier1_contains_hindi(self):
        assert "hi-IN" in TIER1_LANGUAGES

    def test_tier1_contains_tamil(self):
        assert "ta-IN" in TIER1_LANGUAGES

    def test_hinglish_is_hi(self):
        assert HINGLISH[0][0] == "hi-IN"

    def test_tanglish_is_ta(self):
        assert TANGLISH[0][0] == "ta-IN"

    def test_tenglish_is_te(self):
        assert TENGLISH[0][0] == "te-IN"

    def test_banglish_is_bn(self):
        assert BANGLISH[0][0] == "bn-IN"

    def test_marathlish_is_mr(self):
        assert MARATHLISH[0][0] == "mr-IN"


# ── LanguageHint ─────────────────────────────────────────────────────────────

class TestLanguageHint:
    def test_bcp47_stored(self):
        h = LanguageHint(bcp47_code="hi-IN", confidence=0.9)
        assert h.bcp47_code == "hi-IN"

    def test_confidence_stored(self):
        h = LanguageHint(bcp47_code="ta-IN", confidence=0.75)
        assert h.confidence == pytest.approx(0.75)


# ── SessionCapabilities ──────────────────────────────────────────────────────

class TestSessionCapabilities:
    def test_defaults_false(self):
        cap = SessionCapabilities()
        assert cap.dialect_routing is False
        assert cap.code_switch_detection is True  # True is the default

    def test_set_flags(self):
        cap = SessionCapabilities(code_switch_detection=True, dialect_routing=True)
        assert cap.code_switch_detection is True
        assert cap.dialect_routing is True
