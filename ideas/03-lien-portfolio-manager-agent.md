# Lien Portfolio Manager Agent

## The Problem

Personal injury imaging centers have millions of dollars in outstanding liens — scans already performed, payment pending on case settlement. These cases take 6 months to 3+ years to resolve. During that time:

- No one is actively monitoring most cases
- Problems surface only when someone emails (reactive, not proactive)
- Attorney drops a case and the imaging center finds out months later
- Cases age silently toward write-off
- Staff lack bandwidth to track hundreds or thousands of open liens

The lien portfolio is a depreciating asset that nobody is actively managing.

## The Solution: A Continuous Portfolio Management Agent

An always-on AI agent that monitors every outstanding lien, every day.

### Stale Case Detection
- "This lien is 14 months old. The attorney hasn't communicated in 6 months — something is wrong."
- Triggers proactive outreach before the case becomes unrecoverable

### Automated Escalation Sequences
- Polite check-in at 90 days
- Status request at 180 days
- Firmer follow-up at 365 days
- Collections warning at appropriate threshold
- Each step customizable per attorney relationship

### Attorney-Level Intelligence
- "Attorney X has 23 outstanding liens averaging 18 months old. Attorney Y has 15 liens averaging 6 months. X is a collections risk."
- Patterns across firms: payment speed, average recovery rate, negotiation behavior
- Early warning when a previously reliable firm starts going silent

### Drop Case Rapid Response
- When an attorney sends a "we're no longer representing" email, the agent doesn't just tag it
- Immediately initiates lien recovery: identify new attorney, transfer lien, protect the receivable
- Time is critical — the faster you act on a drop, the higher the recovery rate

### Portfolio Valuation
- "Your total outstanding liens are $2.3M. Based on historical collection rates by attorney and case age, expected recovery is $1.7M."
- Identifies the 40 cases most at risk of non-recovery
- Cash flow forecasting: expected inflows by month based on case age distributions

### Settlement Detection
- Monitor attorney communications for settlement signals
- Cross-reference with payment patterns
- Detect when cases are settling before the check arrives (or doesn't)

## Value Proposition

"You have millions in outstanding liens. Right now you find out a case went bad when the attorney finally emails you. What if an AI was watching every case, every day, and catching problems 6 months earlier?"

## Revenue Model

- Percentage of recovered revenue on cases the agent flagged (performance-based)
- Monthly flat fee per active lien managed
- Even a 5% improvement in lien recovery rate on a multi-million dollar portfolio pays for itself many times over

## Leverages Existing Infrastructure

- Lien agent already processes lien documents and communicates with attorneys
- MCP connection to RadFlow provides patient/study/billing data
- FrontApp integration handles all communication
- Classification engine already understands lien-related emails
- Email processing traces provide the communication history

## What's New to Build

- Cross-conversation state tracking (entity timeline per patient/attorney/case)
- Proactive scheduling engine (time-based triggers, not just email-based)
- Portfolio analytics dashboard
- Attorney scoring model
- Settlement signal detection

## Build Effort: Medium

Core agent and data infrastructure exists. Primary new work is the proactive scheduling engine (agents that trigger on time, not just on email) and the cross-conversation state layer.

## Priority: HIGH

Directly extends existing lien automation. Same client, same domain, immediate revenue impact. This is the most natural "next step" for the current product.
