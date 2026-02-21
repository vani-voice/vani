# Vani Conformance Test Suite — README

# VAM/1.0

## Overview

This directory contains the YAML-based conformance test suite for VAM/1.0.
Any implementation claiming to be "VAM/1.0 conformant" MUST pass all tests
marked `level: MUST`. Tests marked `level: SHOULD` and `level: MAY` are
aspirational.

## Running Tests

```bash
# Install dev dependencies
pip install vani[dev]

# Run the full conformance suite against the reference stub
vani-conformance --target stub

# Run against a live gRPC endpoint
vani-conformance --target grpc --endpoint localhost:50051
```

## Test Files

| File                       | What it Tests                                |
| -------------------------- | -------------------------------------------- |
| `session_negotiation.yaml` | SessionInitRequest/Response protocol         |
| `code_switch.yaml`         | CodeSwitchSpan annotation correctness        |
| `turn_signals.yaml`        | TurnSignal state machine ordering            |
| `audio_negotiation.yaml`   | Codec negotiation and downgrade              |
| `action_execution.yaml`    | ActionRequestEnvelope / ActionResultEnvelope |
| `bandwidth_tiers.yaml`     | Tier A / B / C profile adherence             |

## Scoring

| Result | Meaning                                                         |
| ------ | --------------------------------------------------------------- |
| PASS   | Test assertion met                                              |
| FAIL   | MUST-level assertion not met — implementation is non-conformant |
| WARN   | SHOULD-level assertion not met                                  |
| SKIP   | Capability declared as unsupported in SessionInitResponse       |
