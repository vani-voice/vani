# VAM/1.0 — Code-Switching Specification

**Revision:** 1.0-draft · **Date:** 2026-02-18

---

## 1. Overview

Code-switching — the practice of alternating between two or more languages
within a single conversation or sentence — is endemic to Indian speech. It is
not an edge case; it is the dominant communication pattern for educated, urban,
and semi-urban Indian speakers.

This document specifies how Vani gateways MUST handle, annotate, and route
code-switched speech.

---

## 2. Indian Code-Switch Profiles

A `CodeSwitchProfile` is the pairing of a base language and a mixed language.
The following profiles are defined in VAM/1.0:

| Profile ID | Base Language | Mixed Language | Common Name | Speakers |
| ---------- | ------------- | -------------- | ----------- | -------- |
| `hi-en`    | `hi-IN`       | `en-US`        | Hinglish    | ~300M    |
| `ta-en`    | `ta-IN`       | `en-US`        | Tanglish    | ~50M     |
| `te-en`    | `te-IN`       | `en-US`        | Tenglish    | ~60M     |
| `bn-en`    | `bn-IN`       | `en-US`        | Banglish    | ~70M     |
| `mr-en`    | `mr-IN`       | `en-US`        | Marathlish  | ~40M     |
| `kn-en`    | `kn-IN`       | `en-US`        | Kanglish    | ~30M     |
| `ml-en`    | `ml-IN`       | `en-US`        | Manglish    | ~20M     |
| `hi-ur`    | `hi-IN`       | `ur-IN`        | Hindustani  | ~100M    |

Additional profiles MAY be registered by gateways. Unregistered profiles
MUST be treated as `CAPABILITY_UNSUPPORTED` (downgrade to base language only).

---

## 3. Session-Level Code-Switch Declaration

To activate code-switch detection, the client supplies multiple `LanguageHint`
entries in `SessionInitRequest.language_hints`:

```json
{
  "language_hints": [
    { "bcp47_code": "hi-IN", "confidence": 0.7 },
    { "bcp47_code": "en-US", "confidence": 0.3 }
  ],
  "requested_capabilities": {
    "code_switch_detection": true
  }
}
```

If the gateway supports code-switch detection for this profile, it MUST:

1. Set `negotiated_capabilities.code_switch_detection = true` in `SessionInitResponse`
2. Populate `TranscriptEvent.code_switch_spans` on every final transcript

If the gateway does NOT support the requested profile, it MUST:

1. Set `negotiated_capabilities.code_switch_detection = false`
2. Emit `TranscriptEvent` with empty `code_switch_spans`
3. Attempt to transcribe in the highest-confidence base language

---

## 4. CodeSwitchSpan Annotation Semantics

The `CodeSwitchSpan` message (defined in `stream.proto`) annotates character
ranges within a `TranscriptEvent.text` where the language differs from the
primary detected language.

### 4.1 Offset Convention

- Offsets are **Unicode code-point positions** (not UTF-8 byte offsets)
- `start_char` is **inclusive**; `end_char` is **exclusive**
- A span [8, 14] covers characters at positions 8, 9, 10, 11, 12, 13

### 4.2 Annotation Examples

**Example 1 — Hinglish, single word switch:**

```
text:  "मुझे ये laptop बहुत पसंद है"
               ^      ^
               8      14
```

```protobuf
code_switch_spans: [
  { start_char: 8, end_char: 14, language_bcp47: "en-US", confidence: 0.97 }
]
```

The surrounding text ("मुझे ये", "बहुत पसंद है") is in `hi-IN` (the primary
detected language) and requires no span annotation.

**Example 2 — Tanglish, clause-level switch:**

```
text:  "நாளைக்கு meeting இருக்கு, so I'll call you back"
                ^       ^         ^                   ^
                7       14        26                  47
```

```protobuf
code_switch_spans: [
  { start_char: 7,  end_char: 14, language_bcp47: "en-US", confidence: 0.95 },
  { start_char: 26, end_char: 47, language_bcp47: "en-US", confidence: 0.99 }
]
```

**Example 3 — No code-switching (pure Hindi):**

```
text:  "आज मौसम बहुत अच्छा है"
code_switch_spans: []  // empty — no switches detected
```

### 4.3 Roman Transliteration and Code-Switching

When `ScriptPreference = SCRIPT_ROMAN` or `SCRIPT_BOTH`, code-switch offsets
refer to positions in `text_roman`, not `text`. The `text` and `text_roman`
fields may have different lengths; offsets are field-specific.

If `SCRIPT_BOTH` is requested, BOTH `text` and `text_roman` MUST carry
independent `CodeSwitchSpan` annotations (attached to the `text` field by
convention; the gateway MAY add a parallel `code_switch_spans_roman` in a
future revision).

### 4.4 Nested and Overlapping Spans

Spans MUST NOT overlap. If overlapping spans are detected (model artifact),
the gateway MUST resolve by shortest span wins (inner span takes precedence).

---

## 5. LLM Input Format for Code-Switched Transcripts

When the gateway passes a code-switched transcript to the LLM backend, it MUST
include **both** the raw transcript and metadata:

```json
{
  "role": "user",
  "content": "मुझे ये laptop बहुत पसंद है",
  "vani_meta": {
    "primary_language": "hi-IN",
    "code_switches": [
      { "text": "laptop", "language": "en-US", "start": 8, "end": 14 }
    ],
    "text_roman": "mujhe ye laptop bahut pasand hai"
  }
}
```

This allows the LLM to:

1. Understand the full sentence in context
2. Respond in the same mix style as the user (matching register)
3. Use `text_roman` when processing with English-tokenized models

Gateways SHOULD pass `text_roman` to LLMs that are primarily English-trained,
and SHOULD pass native `text` to LLMs explicitly trained on Indian scripts.

---

## 6. Gateway Conformance Requirements for Code-Switch

A VAM/1.0 conformant gateway that claims `code_switch_detection`:

- **MUST** populate `TranscriptEvent.code_switch_spans` on all FINAL transcripts
- **MUST** use Unicode code-point offsets (not bytes)
- **MUST** set `confidence` on each span (value of 0.0 is acceptable if unknown)
- **MUST** handle the case of zero spans (no switching detected) by returning an
  empty list, not omitting the field
- **SHOULD** support at minimum the `hi-en` (Hinglish) profile
- **SHOULD** surface `detected_language_bcp47` at the utterance level even when
  code-switching is present (report the dominant language)
- **MAY** support Tier 2 profiles (`ta-en`, `te-en`, etc.)

---

## 7. AI4Bharat OIWER Alignment

The `CodeSwitchSpan` annotation schema is designed to be compatible with
AI4Bharat's OIWER (Orthographically-Informed Word Error Rate) framework for
code-switched ASR evaluation. Implementations intending to use OIWER benchmarks
can directly map `code_switch_spans` to OIWER span annotations.

Reference: [AI4Bharat OIWER GitHub](https://github.com/AI4Bharat/OIWER)
