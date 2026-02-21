"""
tests/test_conformance_yaml.py — Validate the conformance YAML test files are
well-formed and contain the expected test IDs and required keys.
"""

import pathlib
import re

import pytest
import yaml

CONFORMANCE_DIR = pathlib.Path(__file__).parent.parent / "conformance" / "tests"


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFORMANCE_DIR / name).read_text())


# ── session_negotiation.yaml ─────────────────────────────────────────────────

class TestSessionNegotiationYAML:
    @pytest.fixture(scope="class")
    def suite(self):
        return load_yaml("session_negotiation.yaml")

    def test_has_tests_key(self, suite):
        assert "tests" in suite

    def test_ten_tests(self, suite):
        assert len(suite["tests"]) == 10

    def test_ids_sn_001_to_010(self, suite):
        ids = {t["id"] for t in suite["tests"]}
        for i in range(1, 11):
            assert f"SN-{i:03d}" in ids

    def test_each_test_has_required_keys(self, suite):
        for t in suite["tests"]:
            assert "id" in t
            assert "description" in t
            assert "level" in t         # MUST / SHOULD

    def test_levels_are_valid(self, suite):
        valid = {"MUST", "SHOULD", "MAY"}
        for t in suite["tests"]:
            assert t["level"] in valid


# ── code_switch.yaml ─────────────────────────────────────────────────────────

class TestCodeSwitchYAML:
    @pytest.fixture(scope="class")
    def suite(self):
        return load_yaml("code_switch.yaml")

    def test_has_tests_key(self, suite):
        assert "tests" in suite

    def test_ten_tests(self, suite):
        assert len(suite["tests"]) == 10

    def test_ids_cs_001_to_010(self, suite):
        ids = {t["id"] for t in suite["tests"]}
        for i in range(1, 11):
            assert f"CS-{i:03d}" in ids

    def test_reference_transcripts_present(self, suite):
        assert "reference_transcripts" in suite

    def test_hinglish_reference_transcript(self, suite):
        # reference_transcripts is a dict keyed by id
        refs = suite["reference_transcripts"]
        assert "hinglish_1" in refs
        t = refs["hinglish_1"]
        assert "text" in t
        assert "laptop" in t["text"]  # canonical Hinglish code-switch example


# ── turn_signals.yaml ────────────────────────────────────────────────────────

class TestTurnSignalsYAML:
    @pytest.fixture(scope="class")
    def suite(self):
        return load_yaml("turn_signals.yaml")

    def test_has_tests_key(self, suite):
        assert "tests" in suite

    def test_twelve_tests(self, suite):
        assert len(suite["tests"]) == 12

    def test_ids_ts_001_to_012(self, suite):
        ids = {t["id"] for t in suite["tests"]}
        for i in range(1, 13):
            assert f"TS-{i:03d}" in ids

    def test_latency_constraints_present(self, suite):
        # At least one test name or description should mention latency
        text = " ".join(
            t.get("name", "") + " " + t.get("description", "")
            for t in suite["tests"]
        )
        assert "latency" in text.lower() or "ms" in text
