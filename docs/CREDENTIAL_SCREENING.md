# Credential Screening for RX-Tagged Emails

## Overview

Automatically screen provider credentials on referrals tagged with **RX**. When a referral's provider holds only disallowed credentials, the system applies the `credential review` tag to prevent auto-scheduling and route the referral for manual review.

## Scope

This check applies **only** to emails that have been tagged with **RX** (under Scheduling > RX).

## Goal

Automatically apply the tag **`credential review`** when a referral meets **both** of the following conditions:

1. The provider credentials (from `nameprefix` and/or `namesuffix`) include **at least one** credential from the "NOT allowed to refer" list.
2. The provider credentials include **ZERO** credentials from the "allowed to refer" list.

**Key rule:** If **any** allowed credential is present (e.g., MD, DO, NP, PA), do **NOT** apply the tag, even if disallowed credentials are also present. Allowed always wins.

## Credential Lists

### Allowed Credentials (can refer)

| Credential | Allowed |
|------------|---------|
| MD         | Yes     |
| DO         | Yes     |
| MBBS       | Yes     |
| MBChB      | Yes     |
| NP         | Yes     |
| PA         | Yes     |
| APRN       | Yes     |
| ARNP       | Yes     |
| CRNP       | Yes     |
| FNP        | Yes     |
| AGNP       | Yes     |
| PMHNP      | Yes     |
| DC         | Yes     |
| DPM        | Yes     |
| DDS        | Yes     |
| DMD        | Yes     |
| OD         | Yes     |
| ND         | Yes     |
| CNM        | Yes     |
| CNS        | Yes     |

### Disallowed Credentials (cannot refer)

| Credential | Allowed |
|------------|---------|
| PT         | No      |
| DPT        | No      |
| OCS        | No      |
| SCS        | No      |
| NCS        | No      |
| GCS        | No      |
| WCS        | No      |
| PCS        | No      |
| OT         | No      |
| OTA        | No      |
| SLP        | No      |
| ATC        | No      |
| LAC        | No      |
| PHD        | No      |
| PSYD       | No      |
| RN         | No      |
| LVN        | No      |
| LPN        | No      |
| MA         | No      |
| EMT        | No      |
| PARAMEDIC  | No      |
| LCSW       | No      |
| LMFT       | No      |
| LPC        | No      |
| LMHC       | No      |
| AUD        | No      |
| RRT        | No      |
| PTA        | No      |
| LMT        | No      |
| PHARMD     | No      |

## Implementation Notes

### Credential Normalization

Before matching, normalize each extracted credential token:

1. Convert to **uppercase**
2. Remove all dots (`.`)
3. Remove all spaces

For example: `Pa-C` -> `PA-C` -> strip non-alpha -> `PAC` ... but since `PA` is the base credential, the normalization should match `PA`. Implementation should strip trailing `-C`, `-BC`, etc. suffixes that denote sub-specialties (e.g., `PA-C` -> `PA`).

### Evaluation Logic

1. Extract credentials from both `nameprefix` and `namesuffix` fields.
2. Normalize each credential token.
3. Check each credential against the allowed list first.
4. **Stop evaluation immediately** once an allowed credential is found — the provider is cleared.
5. Only apply the `credential review` tag if the final result contains **disallowed credentials only** (and zero allowed credentials).

### Pseudocode

```
credentials = normalize(extract(nameprefix)) + normalize(extract(namesuffix))

has_allowed = any(c in ALLOWED_LIST for c in credentials)
has_disallowed = any(c in DISALLOWED_LIST for c in credentials)

if has_disallowed and not has_allowed:
    apply_tag("credential review")
```

## Examples

### Allowed (at least one accepted credential — do NOT tag)

| Provider               | Credentials Found | Result                    |
|------------------------|-------------------|---------------------------|
| John Smith, MD         | MD                | ALLOWED (MD)              |
| Jane Doe, NP           | NP                | ALLOWED (NP)              |
| Carlos Rivera, PA-C    | PA                | ALLOWED (PA)              |
| Emily Chen, DPM        | DPM               | ALLOWED (DPM)             |
| Ahmed Hassan, MBBS     | MBBS              | ALLOWED (MBBS)            |

### Not Allowed (only disallowed credentials — apply `credential review` tag)

| Provider                | Credentials Found | Result                    |
|-------------------------|-------------------|---------------------------|
| Sarah Thompson, PT      | PT                | NOT ALLOWED (PT)          |
| Michael Lee, LCSW       | LCSW              | NOT ALLOWED (LCSW)        |
| Rachel Kim, DPT, OCS   | DPT, OCS          | NOT ALLOWED (DPT + OCS)   |
| Brian Adams, RN         | RN                | NOT ALLOWED (RN)          |
| Laura Martinez, PharmD  | PHARMD            | NOT ALLOWED (PHARMD)      |

### Mixed Credentials (allowed wins — do NOT tag)

| Provider                   | Credentials Found | Result                          |
|----------------------------|-------------------|---------------------------------|
| David Wilson, MD, LCSW     | MD, LCSW          | ALLOWED (MD overrides LCSW)     |
| Anna Patel, NP, RN        | NP, RN            | ALLOWED (NP overrides RN)       |
| Robert Johnson, DO, PhD   | DO, PHD           | ALLOWED (DO overrides PhD)      |
| Sophia Nguyen, PA, EMT    | PA, EMT           | ALLOWED (PA overrides EMT)      |
| Mark Hernandez, MBBS, LCSW| MBBS, LCSW        | ALLOWED (MBBS overrides LCSW)   |

## Downstream Effects

When the `credential review` tag is applied, the following actions are triggered:

1. **Auto-scheduling is prevented** for the referral.
2. **"Radiology Referral Credential Review" email template** is triggered.
3. **Referral is routed to manual review.**

## Configuration

The credential lists should be externalized (config/table) rather than hardcoded, to allow easy updates without code changes.
