# Vani India Tool Registry

**Version:** 1.0-draft · **Date:** 2026-02-18

Tools marked ✅ have a canonical schema defined below.
Tools marked 🔜 are planned for a future registry version.

These schemas are MCP-compatible (JSON Schema for `inputSchema`).
Any VAM/1.0 Action Server implementing a registry tool MUST use the exact
`tool_name`, required fields, and response structure defined here.

---

## Registry Tools

| registry_key             | Category    | Status | Data Sensitivity |
| ------------------------ | ----------- | ------ | ---------------- |
| `pan_validate`           | Fintech/KYC | ✅     | HIGH — PAN data  |
| `aadhaar_verify_otp`     | Fintech/KYC | ✅     | HIGH — Aadhaar   |
| `enam_mandi_price`       | Agritech    | ✅     | LOW              |
| `pm_kisan_eligibility`   | Govtech     | ✅     | MEDIUM           |
| `bhashini_translate`     | Language    | ✅     | LOW              |
| `ration_card_lookup`     | Govtech     | ✅     | HIGH             |
| `upi_payment_initiate`   | Fintech     | 🔜     | CRITICAL         |
| `weather_advisory`       | Agritech    | 🔜     | LOW              |
| `hospital_locator`       | Healthcare  | 🔜     | LOW              |
| `scheme_eligibility`     | Govtech     | 🔜     | MEDIUM           |
| `loan_emi_calculator`    | Fintech     | 🔜     | LOW              |
| `crop_disease_diagnosis` | Agritech    | 🔜     | LOW              |

---

## Tool Schemas

---

### `pan_validate`

Validates a PAN (Permanent Account Number) via NSDL/UTI-TSL lookup.

**⚠ Data Residency:** MUST be hosted within India. PAN numbers are not to be
logged at the gateway.

```json
{
  "name": "pan_validate",
  "description": "Validate a PAN card number and retrieve the holder's name and status. Use when a user provides their PAN for KYC or identity verification.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pan_number": {
        "type": "string",
        "pattern": "^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
        "description": "10-character PAN in the format AAAAA9999A"
      },
      "dob": {
        "type": "string",
        "format": "date",
        "description": "Date of birth in YYYY-MM-DD format (required for individual PAN only)"
      }
    },
    "required": ["pan_number"]
  }
}
```

**Expected response (McpToolResult.content[0].text):**

```json
{
  "valid": true,
  "pan_type": "Individual",
  "name_on_pan": "RAMESH KUMAR SHARMA",
  "status": "Active",
  "masked_pan": "ABCDE****A"
}
```

---

### `aadhaar_verify_otp`

Initiates Aadhaar OTP-based authentication via UIDAI's sandbox API.

**⚠ Data Residency:** MUST be IN_ONLY. Aadhaar numbers are classified as
sensitive personal data under DPDP Act 2023. The gateway MUST NOT log the
`aadhaar_number` field.

```json
{
  "name": "aadhaar_verify_otp",
  "description": "Send an OTP to the Aadhaar-linked mobile number for identity verification. Returns a transaction ID; the caller then reads back the OTP.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "aadhaar_number": {
        "type": "string",
        "pattern": "^[0-9]{12}$",
        "description": "12-digit Aadhaar UID"
      }
    },
    "required": ["aadhaar_number"]
  }
}
```

**Expected response:**

```json
{
  "otp_sent": true,
  "txn_id": "TXN-2026-XXXXX",
  "masked_mobile": "XXXXXX7890",
  "expires_in_seconds": 300
}
```

---

### `enam_mandi_price`

Fetches real-time or last-24h commodity prices from the eNAM (National Agriculture Market) API.

```json
{
  "name": "enam_mandi_price",
  "description": "Get the current or most recent wholesale market price for a crop at a specified APMC mandi. Use for farmer queries about crop selling prices.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "crop": {
        "type": "string",
        "description": "Crop name in English or Hindi (e.g., 'wheat', 'gehu', 'tomato', 'tamatar')"
      },
      "mandi": {
        "type": "string",
        "description": "APMC mandi name (e.g., 'Azadpur', 'Vashi', 'Koyambedu')"
      },
      "state": {
        "type": "string",
        "description": "Indian state abbreviation (e.g., 'UP', 'MH', 'TN'). Optional — narrows results if mandi name is ambiguous."
      }
    },
    "required": ["crop", "mandi"]
  }
}
```

**Expected response:**

```json
{
  "crop": "Wheat",
  "crop_hindi": "गेहूं",
  "mandi": "Azadpur",
  "state": "Delhi",
  "min_price_per_quintal": 2250,
  "max_price_per_quintal": 2380,
  "modal_price_per_quintal": 2310,
  "currency": "INR",
  "date": "2026-02-18",
  "source": "eNAM"
}
```

---

### `pm_kisan_eligibility`

Checks PM-KISAN scheme eligibility for a farmer based on land holding and state.

```json
{
  "name": "pm_kisan_eligibility",
  "description": "Check whether a farmer is eligible for PM-KISAN income support scheme and the next installment date.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "aadhaar_last4": {
        "type": "string",
        "pattern": "^[0-9]{4}$",
        "description": "Last 4 digits of Aadhaar for partial identity lookup"
      },
      "mobile_number": {
        "type": "string",
        "pattern": "^[6-9][0-9]{9}$",
        "description": "10-digit Indian mobile number registered with PM-KISAN"
      },
      "state": {
        "type": "string",
        "description": "State of the farmer (e.g., 'Punjab', 'Maharashtra')"
      }
    },
    "required": ["mobile_number", "state"]
  }
}
```

**Expected response:**

```json
{
  "eligible": true,
  "beneficiary_name": "SURESH PATEL",
  "next_installment_date": "2026-04-01",
  "next_installment_amount": 2000,
  "currency": "INR",
  "installment_number": 19,
  "account_linked": true
}
```

---

### `bhashini_translate`

Translate text between any two of the 22 supported Indian languages via Bhashini NMT.

```json
{
  "name": "bhashini_translate",
  "description": "Translate text between Indian languages using Bhashini / AI4Bharat IndicTrans2. Use when the agent needs to relay a message in a different language.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text": {
        "type": "string",
        "description": "Text to translate"
      },
      "source_language": {
        "type": "string",
        "description": "BCP-47 source language code (e.g., 'hi-IN', 'ta-IN')"
      },
      "target_language": {
        "type": "string",
        "description": "BCP-47 target language code"
      }
    },
    "required": ["text", "source_language", "target_language"]
  }
}
```

**Expected response:**

```json
{
  "translated_text": "நாளை மழை பெய்யும்",
  "source_language": "hi-IN",
  "target_language": "ta-IN",
  "model": "IndicTrans2",
  "confidence": 0.93
}
```

---

### `ration_card_lookup`

Look up ration card status and entitlements via the National Food Security Act portal.

**⚠ Data Residency:** MUST be IN_ONLY. Ration card data is sensitive personal
information.

```json
{
  "name": "ration_card_lookup",
  "description": "Look up ration card details, beneficiary list, and next distribution date for a household.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "ration_card_number": {
        "type": "string",
        "description": "State-specific ration card number"
      },
      "state": {
        "type": "string",
        "description": "Indian state (required — ration card numbers are state-scoped)"
      }
    },
    "required": ["ration_card_number", "state"]
  }
}
```

**Expected response:**

```json
{
  "valid": true,
  "card_type": "AAY",
  "head_of_family": "MEENA DEVI",
  "beneficiary_count": 5,
  "monthly_entitlement_kg": 25,
  "commodity": "Rice",
  "next_distribution_date": "2026-03-01",
  "fair_price_shop": "Shop No. 42, Rampur Block"
}
```

---

## Adding Tools to the Registry

To propose a new tool for the registry:

1. Open a GitHub issue with the label `tool-registry`
2. Provide: tool name, category, input JSON schema, expected response shape,
   data sensitivity classification, and reference API endpoint
3. The schema must be reviewed for PII handling, DPDP Act compliance, and
   interoperability with existing tools
4. Upon approval, the tool is merged with a `registry_key` and marked ✅
