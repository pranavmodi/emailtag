# Claims Intelligence Agent (Denial Prevention & Recovery)

## The Problem

After a scan is performed, a claim is submitted to insurance. Denial rates in medical imaging run 10-20%. Each denial requires manual review, correction, and resubmission. Many denied claims are never successfully resubmitted — they become write-offs. For a mid-size imaging center doing 50+ scans/day, this is hundreds of thousands in annual lost revenue.

## The Solution: An AI Agent Managing Every Claim Lifecycle

### Pre-Submission Screening

Before the claim goes out, the agent checks:
- Is the coding correct for this study/diagnosis combination?
- Does this payer require a modifier for this CPT code?
- Is the diagnosis code consistent with the study type?
- Has this payer been denying this code combination recently?

Fix it before it gets denied. Shift from reactive appeals to proactive denial prevention.

### Denial Pattern Learning

"UnitedHealthcare has denied 73% of CPT 72148 (MRI lumbar without contrast) claims when paired with diagnosis M54.5 (low back pain) in the last 90 days. They're likely applying a new medical necessity policy. Switch to M54.51 (vertebrogenic low back pain) which has a 94% approval rate for the same study."

The agent learns these patterns across all claims processed and applies them before submission.

### Automated Appeals

When a denial comes in, the agent:
1. Classifies the denial reason (not medically necessary, missing info, coding error, timely filing)
2. Generates the appropriate appeal with supporting documentation
3. Submits it — within hours, not weeks
4. Tracks the appeal through resolution

### Underpayment Detection

"Blue Cross paid $380 for this MRI. The contracted rate is $420. This is a $40 underpayment. Filed automated underpayment dispute."

Multiply by thousands of claims per year. Most imaging centers don't catch these.

### Timely Filing Watchdog

Every payer has a filing deadline (90-365 days). The agent tracks every claim and ensures nothing ages out. A single missed filing deadline on a $2,000 MRI is money that can never be recovered.

## Value Proposition

"What percentage of your claims get denied on first submission? What percentage of denials do you successfully appeal? What if an AI caught 60% of denials before they happened, and automatically appealed the ones that got through?"

## Revenue Model

- Percentage of recovered revenue on denials that would have been write-offs
- Per-claim processing fee for pre-submission screening
- Performance-based pricing makes the ROI conversation trivial: "The agent recovered $50K in claims that would have been written off. Our cut is 10%."

## Key Metrics to Track

- First-pass claim acceptance rate (before vs. after)
- Average days to payment
- Denial rate by payer/CPT code
- Appeal success rate
- Total recovered revenue from prevented denials
- Underpayment recovery amount

## Build Effort: Medium-High

Requires payer clearinghouse integrations (Availity, Change Healthcare, etc.) and claims data ingestion from the practice management system. Core agent and MCP infrastructure already exists.

## Priority: HIGH

Natural complement to Prior Auth Agent — together they cover the full insurance revenue cycle. Prior auth prevents pre-service denials, claims intelligence prevents post-service denials.
