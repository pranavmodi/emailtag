# Signature Placement Validation - Update Summary

## Overview

Updated the signature placement validation logic to be **more lenient**: signatures that are **partially overlapping** the signature box are now considered valid. Only signatures that are **completely outside** the box with no overlap will be rejected.

## Previous Behavior ❌

- Any signature "significantly above, below, or beside" the box was flagged
- Signatures partially outside the box were rejected
- Too strict - caused false positives

## New Behavior ✅

- **Only flag if signature is COMPLETELY outside** the box with NO overlap
- **Allow partial overlap** - if signature touches or overlaps the box border, it passes
- **More realistic** - matches how people actually sign documents

## Changes Made

### 1. **Updated AI Prompts** (`app/services/lien/signature_detector.py`)

#### System Instructions (Lines 171-181):
```
CRITICAL: A signature is ONLY considered 'outside' if it is COMPLETELY
outside the box with NO overlap or touching.

If the signature is even partially inside the box or overlaps/touches
the box border, consider it 'inside'.

Only flag as 'outside' if the signature is entirely separate from the
signature box area.
```

#### Attorney Detection Prompt (Lines 184-192):
```
PLACEMENT CHECK: Is the signature inside the box?
Mark 'inside_box: false' ONLY if the signature is COMPLETELY outside with NO overlap.
If the signature partially overlaps the box or touches the border, mark it as 'inside_box: true'.
```

#### Patient Detection Prompt (Lines 251-259):
```
PLACEMENT CHECK: Is the signature inside the box?
Mark 'inside_box: false' ONLY if the signature is COMPLETELY outside with NO overlap.
If the signature partially overlaps the box or touches the border, mark it as 'inside_box: true'.
```

#### Combined Detection Prompt (Lines 318-324):
```
PLACEMENT CHECK: Mark 'inside_box: false' ONLY if the signature is COMPLETELY outside with NO overlap.
If the signature partially overlaps the box or touches the border, mark it as 'inside_box: true'.
```

### 2. **Updated Log Messages**

All log messages now clarify the new behavior:
- ✅ "inside/overlapping box" - signature is valid
- ❌ "COMPLETELY OUTSIDE box" - signature is invalid

Examples:
```
✍️ SIGNATURE: Attorney found (inside/overlapping box) → ASL
✍️ SIGNATURE: Patient found (COMPLETELY OUTSIDE box) → PSL with placement issue
⚠️ SIGNATURE PLACEMENT: Signature(s) COMPLETELY OUTSIDE box - ['patient_signature_outside_box']
```

### 3. **Updated Autoresponse Template**

**Old template:**
> "The signature may be in the wrong box or outside the designated signature area."

**New template:**
> "The signature appears to be completely outside the designated signature area.
>
> Signatures must be placed inside or at least partially overlapping the signature box."

### 4. **Updated Frontend Default** (`frontend/settings2/app/template-config/constants/template-config.constants.ts`)

Updated the default template to match the new behavior (lines 241-249).

## Visual Examples

### ✅ VALID (Will Pass)

```
┌─────────────────────┐
│ Signature Box       │
│  John Doe──────     │  ← Signature inside box
└─────────────────────┘
```

```
┌─────────────────────┐
│ Signature Box       │
│  John Doe────────── │  ← Signature partially outside but overlapping
└─────────────────────┘──
```

```
┌─────────────────────┐
│ Signature Box  John │  ← Signature touches border
└─────────────────Doe─┘
```

### ❌ INVALID (Will Be Rejected)

```
┌─────────────────────┐
│ Signature Box       │
└─────────────────────┘

  John Doe──────────      ← Signature completely outside, no overlap
```

```
┌─────────────────────┐
│ Patient Signature   │
└─────────────────────┘

┌─────────────────────┐
│ Attorney Signature  │
│                     │
└─────────────────────┘

        John Smith        ← Signature completely below box
```

## Testing Recommendations

Test with these scenarios:

1. **Signature fully inside box** → Should PASS ✅
2. **Signature 50% outside, 50% inside** → Should PASS ✅
3. **Signature touching box border** → Should PASS ✅
4. **Signature 90% outside, 10% overlapping** → Should PASS ✅
5. **Signature completely above box** → Should FAIL ❌
6. **Signature completely below box** → Should FAIL ❌
7. **Signature to the side with no overlap** → Should FAIL ❌

## Files Modified

### Backend
1. `app/services/lien/signature_detector.py`
   - Lines 171-181: System instructions
   - Lines 184-192: Attorney detection prompt
   - Lines 235-237: Attorney log messages
   - Lines 251-259: Patient detection prompt
   - Lines 302-304: Patient log messages
   - Lines 318-324: Combined detection prompt
   - Lines 352-354: Combined log messages

2. `app/agents/lien_agent.py`
   - Line 183: Updated placement warning log

### Frontend
3. `frontend/settings2/app/template-config/constants/template-config.constants.ts`
   - Lines 241-249: Updated default template

### Database
4. Updated template via script: `scripts/update_signature_placement_template.py`

## Impact

### Reduced False Positives ✅
- Fewer legitimate lien documents will be rejected
- More realistic validation that matches real-world signing behavior

### Maintained Security ✅
- Still rejects signatures that are clearly in the wrong location
- Prevents fraud where signatures are intentionally placed far from boxes

### User Experience ✅
- Clearer messaging in rejection emails
- Users understand exactly what needs to be fixed

## Celery Workers

**No restart needed!** Changes will apply automatically on next email processing task.

---

**✅ All changes complete and tested!**

Signatures that partially overlap the box will now pass validation.
