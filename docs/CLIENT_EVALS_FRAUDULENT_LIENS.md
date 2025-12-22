# Client Evaluation Scenarios - Fraudulent Liens

## Overview

Added 9 new test scenarios (scenarios 42-50) to the client evaluation suite to test the system's ability to detect and reject fraudulent or modified lien documents.

## New Scenarios Added

### Fraudulent Document Scenarios (42-48)

These scenarios test the system's ability to detect modifications in actual fraudulent lien documents from the `data/documents/fraudulentliens/` directory:

1. **Scenario 42**: Victoria Concepcion Orozco (LB 254676)
   - File: `(LB) 254676 - Victoria Concepcion Orozco -SIGNED LIEN.pdf`
   - Tests: Conditional language and modifications detection

2. **Scenario 43**: Dhunna Notice of Lien
   - File: `10.01.25 Dhunna fr Precise Imaging re Notice of Lien.pdf`
   - Tests: Non-standard lien format with cover letter conditions

3. **Scenario 44**: Fraudulent Lien (2d5f56bb)
   - File: `2d5f56bbbb6051603dc2133c3d0769eb99f40d99.pdf`
   - Tests: Modifications and conditional language detection

4. **Scenario 45**: LT Atkinson (6.9.2008)
   - File: `6.9.2008 LT Atkinson.pdf`
   - Tests: Old fraudulent lien document detection

5. **Scenario 46**: Fraudulent Lien (6622f1e6)
   - File: `6622f1e6eae239d18d64afb8941b19bae6d7242e.pdf`
   - Tests: Non-standard lien format detection

6. **Scenario 47**: Case 253099 Tech Lien
   - File: `AR-Precise Imaging- Tech Lien-253099-SIGNED.pdf`
   - Tests: Modifications in tech lien documents

7. **Scenario 48**: Palomo Lien
   - File: `palomo.pdf`
   - Tests: Modifications and human review flagging

### Conditional Language Scenarios (49-50)

These scenarios test the new cover letter and email content analysis features:

8. **Scenario 49**: Email with Conditional Language
   - Tests: Email body text analysis for conditional language
   - Expected behavior: Rejection BEFORE document analysis
   - Conditional phrases:
     - "subject to final approval by our managing attorney"
     - "will only proceed if you agree to modify the payment terms"
     - "require that you provide weekly status updates"

9. **Scenario 50**: Cover Letter with Conditional Terms
   - Tests: Cover letter page detection and conditional language analysis
   - Expected behavior: Rejection after document analysis detects cover letter conditions

## Expected Results

All scenarios 42-50 should result in:

**Tags Applied**:
- "Lien Modified"
- "AI: Human review required"

**Autoresponse**:
- System sends modified lien rejection template
- Explains that lien agreements cannot be modified
- Requests resubmission with standard form

**Processing**:
- Document NOT uploaded to RadFlow
- Requires human intervention

## Testing These Scenarios

Run the client evaluation suite:

```bash
emailtag/bin/python scripts/evals/run_client_evals.py
```

Or test specific scenarios:

```bash
# Test scenario 42 (Victoria Concepcion Orozco)
emailtag/bin/python scripts/evals/run_client_evals.py --scenario 42

# Test scenarios 42-48 (all fraudulent documents)
emailtag/bin/python scripts/evals/run_client_evals.py --scenario 42-48

# Test scenarios 49-50 (conditional language)
emailtag/bin/python scripts/evals/run_client_evals.py --scenario 49-50
```

## What These Scenarios Test

### 1. Strikethrough Detection
- Fraudulent documents often contain crossed-out or struck-through text
- System should detect visual strikethrough marks using OpenAI Vision

### 2. Cover Letter Analysis
- Fraudulent submissions may include cover letters with modification language
- System analyzes pages without barcodes for conditional language

### 3. Email Content Analysis
- Emails may contain conditional language in the body text
- System analyzes email content BEFORE processing attachments

### 4. Template Validation
- Fraudulent documents may use non-standard templates
- System should flag documents that deviate from approved templates

### 5. Multi-Layer Detection
The system checks for modifications at multiple levels:
1. Email body text (Scenario 49)
2. Cover letter pages (Scenario 50)
3. Document strikethrough marks (Scenarios 42-48)
4. Template structure (Scenarios 42-48)

## Integration with Existing Tests

These scenarios complement the existing test suite:

- **Scenarios 1-7**: Basic email tagging (apt status, payment, etc.)
- **Scenarios 8-40**: Clean lien processing (PSL, ASL, RAD, TECH)
- **Scenario 41**: Strikethrough detection
- **Scenarios 42-50**: Fraudulent lien detection (NEW)

## Success Metrics

For each fraudulent lien scenario (42-50), the system should:

1. ✅ **Detect the modification/conditional language**
2. ✅ **Apply correct tags** ("Lien Modified", "AI: Human review required")
3. ✅ **Send autoresponse** with rejection message
4. ✅ **Prevent upload** to RadFlow
5. ✅ **Log conditional phrases** found for human review

## Real-World Impact

These test scenarios validate that the system can:

- **Protect against fraud**: Prevent fraudulent liens from being automatically uploaded
- **Enforce standards**: Ensure only approved lien templates are accepted
- **Save time**: Automatically flag problematic submissions for human review
- **Maintain compliance**: Ensure lien agreements meet legal requirements

## File Locations

- **Scenarios Definition**: `/home/fret/work/emailtag/scripts/evals/scenarios_client_evals.py`
- **Fraudulent Documents**: `/home/fret/work/emailtag/data/documents/fraudulentliens/`
- **Test Runner**: `/home/fret/work/emailtag/scripts/evals/run_client_evals.py`

## Related Documentation

- [Cover Letter Detection](./COVER_LETTER_CONDITIONAL_LANGUAGE_DETECTION.md)
- [Lien Modification Detection](./LIEN_MODIFICATION_DETECTION.md)
- [Lien Agent Workflow](./LIEN_AGENT_WORKFLOW.md)
