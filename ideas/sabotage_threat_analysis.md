# Sabotage Threat Analysis: EmailTag System

Identifies small, hard-to-detect changes that could silently degrade or break the email classification pipeline. Focused on changes that **masquerade as prompt tuning issues** — the most dangerous class because the natural response is to rewrite prompts rather than investigate code tampering.

---

## Tier 1 — Near-Perfect Disguise

These would almost certainly be diagnosed as "the LLM is underperforming, let's adjust the prompts" rather than "someone changed the code."

---

### 1. Downgrade fallback model

**File:** `classification_service.py:609`
**Change:** `"gpt-5-mini"` fallback → `"gpt-4o-mini"` or `"gpt-3.5-turbo"`

- **Why it looks like a prompt issue:** Classification accuracy drops across the board, but not to zero. The system still returns plausible-looking tags — just wrong ones 15-30% more often. The natural response is "our prompts need to be more explicit" or "we need more few-shot examples."
- **Why it's hard to catch:** The model name is a *fallback* — it only activates when the primary env vars aren't set, which may happen after a deployment or environment rebuild. Logs say `model=gpt-3.5-turbo` but nobody checks unless they know to look.
- **Detection:** Log model name per call; alert on unexpected models.

---

### 2. Change reasoning_effort from `"medium"` to `"low"`

**File:** `classification_service.py:653-660`

- **Why it looks like a prompt issue:** GPT-5 with `low` reasoning still produces structured JSON, still picks from valid options — just makes more mistakes on ambiguous cases. The team sees edge-case misclassifications and thinks "we need clearer rules for these ambiguous emails."
- **Why it's hard to catch:** The parameter isn't logged by default. The output *format* is correct; only the *accuracy* degrades.
- **Detection:** Log all LLM parameters; eval suite with accuracy thresholds.

---

### 3. Increase temperature from `0.0` to `0.3`

**File:** `classification_service.py:665`

- **Why it looks like a prompt issue:** Non-deterministic results. The same email classified differently on reprocess. Team thinks "the prompt is ambiguous, the model can't decide" and starts rewriting rules. They'll never find the real cause because prompts *are* somewhat ambiguous — just not enough to cause this at `temperature=0.0`.
- **Why it's hard to catch:** `0.3` isn't obviously wrong. It's a "reasonable" value. The effect is statistical — you only notice it by running the same input twice and seeing divergent outputs.
- **Detection:** Run determinism test (same input twice, compare).

---

### 4. Subtle wording swap in rule files

**File:** e.g. `ROOT_SCHEDULING.txt:16`
**Change:** `Scheduling request: ACTION to book/schedule` → `Scheduling request: STATUS inquiry about completion`

- **Why it looks like a prompt issue:** It literally IS a prompt issue — just not an accidental one. The team sees "scheduling requests are being classified as RX" and thinks the wording is unclear. They'll rewrite the rule, probably fixing it — but they'll never know it was sabotage. And the attacker can do it again.
- **Why it's hard to catch:** Rule files are expected to be edited. There's no clear "before" state to compare against unless checksums are enforced.
- **Detection:** SHA-256 checksums of rule files; mandatory eval on change.

---

### 5. Add "If unsure, classify as No Tag" to any rule file

**File:** Any `ROOT_*.txt`

- **Why it looks like a prompt issue:** "No Tag" rate increases gradually. Team thinks the prompts don't cover enough edge cases and starts adding more examples/rules to each category. This is a hamster wheel — no amount of prompt tuning fixes a safety net that catches everything the model hesitates on.
- **Why it's hard to catch:** "If unsure" feels like a reasonable instruction. Someone reviewing the prompt might even think it's *good practice*.
- **Impact:** Emails that get "No Tag" are marked `is_processed=True` at `email.py:1124-1130` and silently never acted on.
- **Detection:** Monitor "No Tag" rate; review all rule file diffs.

---

### 6. Reduce conflict detection window

**File:** `classification_service.py:847-850`
**Change:** `messages[-3:]` → `messages[-1:]`

- **Why it looks like a prompt issue:** Multi-topic emails stop being flagged. Team thinks "the conflict detection prompt needs to be smarter about catching multiple topics." They'll rewrite the conflict detection prompt extensively, never realizing the model only sees the last message and literally cannot detect conflicts in earlier messages.
- **Why it's hard to catch:** The change is `3` → `1` in a slice. It's a one-character diff.
- **Detection:** Eval suite with known multi-topic emails.

---

## Tier 2 — Plausible Disguise (Takes Longer to Misdiagnose)

These might eventually lead someone to look deeper, but the first reaction is still "prompt problem."

---

### 7. Degrade image quality (JPEG quality or DPI)

**File:** `document_processing_service.py:108,121`
**Change:** JPEG quality `75` → `5`, or DPI `200` → `20`

- **Why it looks like a prompt issue:** Document analysis returns wrong types. "The vision model keeps calling liens 'other'" → team rewrites the document classification prompt with more examples. Nothing improves because the model literally can't read the images.
- **What eventually exposes it:** Someone manually inspects the images being sent to the API and notices they're unreadable. But this could take weeks if nobody thinks to check.
- **Detection:** Log image dimensions/sizes; sample visual inspection.

---

### 8. Raise small image threshold

**File:** `document_processing_service.py:165`
**Change:** `20KB` → `200KB`

- **Why it looks like a prompt issue:** Many documents return `"other"` with confidence `0.1`. Team thinks "the model doesn't understand these document types" and adds more document type examples to the prompt. Real cause: images never reach the model.
- **What eventually exposes it:** Someone notices the confidence is always exactly `0.1` for these cases (the hardcoded bypass value), not a model-generated score.
- **Detection:** Monitor `confidence=0.1` rate; track doc analysis bypass rate.

---

### 9. Reduce max_tokens from `200` to `15`

**File:** `classification_service.py:667`

- **Why it looks like a prompt issue:** JSON responses get truncated. `{"chosen_option": "Sched` → parse fails → falls back to `.strip()` → garbage → human review. Team thinks "the model is returning malformed JSON, we need to constrain the output more." They add more prompt instructions about format, which makes the response LONGER, making truncation WORSE.
- **What eventually exposes it:** Someone enables `CLASSIFICATION_DEBUG` and sees the raw truncated responses. But the default is `False`.
- **Detection:** Enable `CLASSIFICATION_DEBUG`; monitor JSON parse failure rate.

---

### 10. Reduce PDF page limit

**File:** `document_processing_service.py:125`
**Change:** `15MB` → `150KB`

- **Why it looks like a prompt issue:** Multi-page lien packets only have the cover letter analyzed. Model says "case_update" or "other" because the cover letter isn't clearly a lien. Team rewrites the document prompt to "pay attention to cover letters that precede liens." Real cause: the actual lien pages were never sent.
- **What eventually exposes it:** Someone compares "pages analyzed" to "total pages" and notices multi-page docs only have 1 page processed.
- **Detection:** Log pages-analyzed vs pages-total per document.

---

## Tier 3 — Short-Lived Disguise

These cause more dramatic symptoms that lead to code investigation faster, but the *initial* reaction might still be "prompt issue."

---

### 11. Add extra character to `.strip()` call

**File:** `classification_service.py:303`
**Change:** `.strip("'\"")`  → `.strip("'\"S")`

- **Why it briefly looks like a prompt issue:** "Scheduling" → "cheduling" → validation failure. Team sees 100% of scheduling emails going to human review and thinks "the model stopped returning 'Scheduling.'"
- **What exposes it quickly:** It affects *only* Scheduling (starts with S). Medical Records and Accounts Receivable still work. This asymmetry is a clue.
- **Detection:** Unit tests that assert exact parsed outputs for each category name.

---

### 12. Broaden autoresponse marker

**File:** `webhooks.py:220` or `config.py:84`
**Change:** Full 4-char Unicode marker → single `"\u200B"`

- **Why it briefly looks like a prompt issue:** Email volume drops. Fewer classifications happening. Team might initially think "we're getting fewer emails" or look at prompt changes.
- **What exposes it:** The webhook logs show `"autoresponse detected"` for real emails. Someone eventually reads those logs.
- **Detection:** Monitor webhook-received vs emails-processed ratio.

---

## Additional Non-Prompt Sabotage Vectors Worth Tracking

These don't look like prompt issues but are still high-impact and hard to detect:

| Vector | File | Impact |
|--------|------|--------|
| Flip tag visibility filter (`== True` → `== False`) | `frontapp_service.py:722` | All tag applications silently use archived tags. Nothing gets tagged. |
| Reverse conflicting tag removal logic | `classification_service.py:1299` | Removes correct new tags, keeps old wrong ones |
| Change queue name (`'emails'` → `'email'`) | `webhooks.py:384` | Tasks sent to nonexistent queue, pile up forever |
| Set `CONFLICT_DETECTION_ENABLED=False` in env | `.env` | Multi-topic emails never flagged for human review |
| Flip archive check (`if archived` → `if not archived`) | `email.py:558` | All active conversations skipped |
| Add common domain to internal filter (e.g. `@gmail.com`) | `config.py:92` | All Gmail senders silently discarded |
| Break lien double-tagging (remove intermediate tag) | `classification_service.py:1217` | Lien dept can't filter by PSL/ASL |
| Swap `chosen_option` to `choosen_option` (typo) | `classification_service.py:723` | JSON field mismatch, falls back to garbage |
| Downgrade document analysis model (`o3` → `gpt-3.5-turbo`) | `.env` / `config.py:128` | Document type detection severely degraded |

---

## Recommended Detection Framework

### Layer 1 — Integrity Checks (Pre-runtime)
- SHA-256 hash all prompt rule files at build time; verify at startup
- Git pre-commit hook: require 2+ reviewers for `prompts/rules/`, `config.py`, `classification_service.py`
- CI pipeline: run full eval suite on every PR

### Layer 2 — Runtime Monitoring (Real-time)
- Log and alert on: model names, temperatures, max_tokens, reasoning_effort for every LLM call
- Track tag distribution hourly; alert on >10% deviation from 7-day rolling average
- Monitor queue depths and consumption rates
- Track webhook-received → email-processed → classification-completed → tag-applied funnel

### Layer 3 — Output Validation (Post-classification)
- Sample N emails/day for human review, compare to AI classification
- Run known-labeled test emails through the system daily (synthetic canaries)
- Alert on "Human review required" rate exceeding threshold
- Alert on "No Tag" rate exceeding threshold

### Layer 4 — Behavioral Anomaly Detection
- Track per-category classification rates; alert on sudden shifts
- Monitor autoresponse loop detection (same conversation getting multiple responses)
- Track document type distribution; alert on spikes in "other" or "unknown"
- Monitor average processing time per email; sudden drops indicate short-circuits

---

## Key Takeaway

The most dangerous vectors share three properties:

1. **The output format is correct** — valid JSON, valid tag names, proper API calls. No errors in logs.
2. **The degradation is statistical** — accuracy drops 15-30%, not 100%. Some emails still classified correctly.
3. **The natural diagnosis is "prompt engineering"** — because the team is used to tuning prompts, it's the first tool they reach for.

The single best defense is an **automated eval suite with accuracy thresholds** that runs on every deployment. If classification accuracy on a known test set drops below X%, the deploy is blocked — regardless of whether the change was to prompts, code, or config.
