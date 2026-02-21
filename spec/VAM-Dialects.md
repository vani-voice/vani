# VAM/1.0 — Dialect Routing Specification

**Revision:** 1.0-draft · **Date:** 2026-02-18

---

## 1. Overview

Standard Indian language ASR models are primarily trained on "textbook" or
urban register speech. A farmer from Bhojpuri-speaking Bihar speaking Hindi
will have a Word Error Rate 2–3× higher than a Delhi Hindi speaker on the
same model. Dialect-aware routing is the mechanism by which Vani gateways
can automatically direct calls to specialized models when dialectal speech
is detected, without requiring the caller to self-identify their dialect.

---

## 2. Dialect Tag Taxonomy

Dialect tags use the format: `{bcp47_base}-{DialectKey}`.
They appear in `TranscriptEvent.dialect_tag`.

### 2.1 Hindi (hi-IN) Dialects

| Dialect Tag               | Region               | Distinctive Features                         |
| ------------------------- | -------------------- | -------------------------------------------- |
| `hi-IN-Standard`          | Delhi NCR, Mumbai    | Broadcast Hindi; default model target        |
| `hi-IN-Bhojpuri`          | Eastern UP, Bihar    | ई/ऊ lengthening, retroflex-heavy             |
| `hi-IN-Awadhi`            | Central UP (Lucknow) | ई/ए merger, distinct verb paradigms          |
| `hi-IN-Braj`              | Mathura/Agra belt    | Archaic morphology, ओ/औ variation            |
| `hi-IN-Haryanvi`          | Haryana              | Retroflex fricatives, distinctive intonation |
| `hi-IN-Rajasthani`        | Rajasthan            | Aspirate mergers, oral-nasal vowel shifts    |
| `hi-IN-Chhattisgarhi`     | Chhattisgarh         | Tone distinctions absent in standard Hindi   |
| `hi-IN-Marathi-Inflected` | Maharashtra border   | Marathi phonology in Hindi speech            |

### 2.2 Tamil (ta-IN) Dialects

| Dialect Tag                | Region                  | Distinctive Features                           |
| -------------------------- | ----------------------- | ---------------------------------------------- |
| `ta-IN-Standard`           | Chennai broadcast Tamil | Literary/formal register; default model target |
| `ta-IN-Madurai`            | Southern Tamil Nadu     | Retroflex-lateral ழ் distinctive; rural flavor |
| `ta-IN-Coimbatore`         | Western Tamil Nadu      | Kongu dialect; phonological simplifications    |
| `ta-IN-Jaffna`             | Northern Sri Lanka      | Archaic consonant distinctions preserved       |
| `ta-IN-Chennai-Colloquial` | Chennai streets         | High English code-mixing; fast speech rate     |

### 2.3 Telugu (te-IN) Dialects

| Dialect Tag         | Region                 | Distinctive Features                           |
| ------------------- | ---------------------- | ---------------------------------------------- |
| `te-IN-Standard`    | Hyderabad broadcast    | Default model target                           |
| `te-IN-Coastal`     | Vizag, Guntur, Krishna | Rhythmically distinct; Urdu loanword influence |
| `te-IN-Rayalaseema` | Kurnool, Cadapa region | Retroflex and alveolar distinctions            |
| `te-IN-Telangana`   | Telangana state        | Urdu/Hindi heavy borrowing; phonemic mergers   |

### 2.4 Bengali (bn-IN) Dialects

| Dialect Tag         | Region                 | Distinctive Features                              |
| ------------------- | ---------------------- | ------------------------------------------------- |
| `bn-IN-Standard`    | Kolkata broadcast      | Default model target                              |
| `bn-IN-Rarhi`       | West Bengal heartland  | Classical standard register                       |
| `bn-IN-Sylheti`     | Sylhet origin speakers | Tonal distinctions, simplified consonant clusters |
| `bn-IN-Rarhi-Rural` | Rural West Bengal      | Slower cadence, more conservative phonology       |

### 2.5 Marathi (mr-IN) Dialects

| Dialect Tag        | Region                    | Distinctive Features                           |
| ------------------ | ------------------------- | ---------------------------------------------- |
| `mr-IN-Standard`   | Pune/Mumbai               | Default model target; heavily Hindi-influenced |
| `mr-IN-Konkan`     | Konkan coast              | Konkani phonological influence                 |
| `mr-IN-Vidarbha`   | Nagpur / East Maharashtra | Distinct retroflex patterns                    |
| `mr-IN-Marathwada` | Aurangabad belt           | Urdu-inflected loanwords                       |

---

## 3. Dialect Detection and Routing Algorithm

### 3.1 Detection

When `SessionCapabilities.dialect_routing = true`, the gateway MUST attempt
dialect detection during the first utterance of a session. Detection MAY use:

1. **Acoustic features**: Pitch contours, formant patterns, retroflexion markers
2. **Lexical markers**: Dialect-specific vocabulary (GEOGRAPHICAL_NER approach)
3. **Phoneme distribution**: N-gram patterns over phoneme sequences

The detected dialect is surfaced in `TranscriptEvent.dialect_tag`.

### 3.2 Routing Decision

```
IF dialect_tag is set
  AND a dialect-specific ASR model is registered for this dialect
  AND the caller's ModelPreference includes the backend that offers this model
THEN
  re-route remaining audio for this session to the dialect-specialized model
ELSE
  continue with the standard model for the base language
```

Dialect routing decisions MUST be logged at the gateway for audit purposes.
Re-routing MUST NOT cause the audio stream to be interrupted or repeated.
The gateway MAY request a brief end-of-speech pause before switching models
(max 150ms) to avoid splitting an utterance across models.

### 3.3 Dialect Routing Notification

When the gateway switches to a dialect-specialized model, it MUST emit a
`TurnSignal` with metadata indicating the dialect change:

```protobuf
TurnSignal {
  event: TURN_EVENT_LISTENING,
  // metadata field (not in v1 proto — gateway MAY use stream_error with is_fatal=false
  // as a notification channel until TurnSignal.metadata is added in v1.1)
}
```

---

## 4. AI4Bharat Lahaja Dataset Alignment

The dialect taxonomy in this specification is aligned with the AI4Bharat
**Lahaja** dataset, which focuses specifically on dialectal Hindi ASR.
Implementers using IndicWhisper or other AI4Bharat models should map
Vani dialect tags to Lahaja speaker metadata fields.

Reference: [AI4Bharat Lahaja](https://github.com/AI4Bharat/Lahaja)

---

## 5. Conformance

A gateway that sets `negotiated_capabilities.dialect_routing = true` MUST:

- Emit `TranscriptEvent.dialect_tag` on at least the first final transcript
  of each session (even if the tag is `{lang}-Standard` indicating no
  non-standard dialect was detected)
- Document which dialect models are available in its server manifest

A gateway MAY return an empty `dialect_tag` if dialect detection is not
available for a specific language pair, without penalizing conformance score —
PROVIDED that `dialect_routing` was declared as `false` in `SessionInitResponse`.
