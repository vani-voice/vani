# Changelog

All notable changes to the Vani protocol and reference implementation are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- `proto/vani/v1/session.proto` — session negotiation messages (SessionInitRequest/Response, LanguageHint, AudioProfile, ModelPreferences, SessionCapabilities)
- `proto/vani/v1/stream.proto` — bidirectional streaming messages (AudioChunk, TranscriptEvent with CodeSwitchSpan, TurnSignal, SynthesisRequest/Chunk)
- `proto/vani/v1/action.proto` — action gateway messages wrapping MCP tool calls over the VAM gRPC stream
- `spec/VAM-Overview.md` — protocol overview and actor model
- `spec/VAM-CodeSwitch.md` — code-switching specification for Indian language mixing
- `spec/VAM-Dialects.md` — dialect routing taxonomy for Tier 1 languages
- `spec/VAM-Transport.md` — three-tier bandwidth-adaptive transport profiles
- `spec/VAM-Actions.md` — MCP-based action execution specification
- `spec/IndiaToolRegistry.md` — canonical MCP tool schemas for Indian govtech/fintech/agritech
- `vani/` — Python package skeleton with abstract backend base classes
- `conformance/` — YAML-based conformance test suite for VAM/1.0 implementations
- `examples/` — runnable example pipelines for Hinglish and Tamil IVR
