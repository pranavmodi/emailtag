# Attorney Relationship Management Agent

## The Problem

For PI-focused imaging centers, attorney referrals are the lifeblood of the business. A handful of high-volume law firms likely generate 50-70% of revenue. Yet most imaging centers have:

- No systematic tracking of referral volume trends per firm
- No early warning when a key firm starts sending fewer patients
- No data on which firms pay fastest vs. slowest
- No understanding of the true profitability of each attorney relationship
- Reactive relationship management — problems surface when it's too late

Losing a single high-volume referring firm to a competitor could cost hundreds of thousands per year. There's usually no warning.

## The Solution: A Continuous Relationship Intelligence Agent

### Referral Volume Monitoring

- Track referral count per firm over time (weekly, monthly, quarterly trends)
- Detect declines early: "Firm X sent 8 referrals/month last year but only 2/month this quarter"
- Alert account managers before the relationship is lost
- Distinguish between seasonal variation and genuine decline

### Attorney/Firm Scoring

Score each relationship on multiple dimensions:
- **Volume**: How many patients do they send?
- **Payment speed**: How quickly do cases settle and pay?
- **Recovery rate**: What percentage of billed amount is actually collected?
- **Administrative burden**: How many back-and-forth emails per case?
- **Document quality**: Are liens properly filled out? How often are modifications detected?

Composite score = referral volume x payment speed x average recovery rate

### Payment Pattern Analysis

- "When Attorney Y handles PI cases, average lien recovery is 72%. When Attorney Z handles similar cases, it's 91%. Factor this into collection priority."
- Identify firms that consistently negotiate aggressively vs. those that pay promptly
- Inform negotiation strategy: know your BATNA before the conversation starts

### New Firm Detection

- "3 emails this month from a law firm we've never worked with. They're sending well-formatted lien paperwork."
- Flag potential new referral sources worth nurturing
- Provide context: firm size, practice areas, geographic coverage

### Proactive Relationship Maintenance

- Generate periodic status reports for high-value firms: "Here's a summary of all cases for your clients currently in process"
- Trigger outreach when a firm's cases are all progressing smoothly: "All 12 of your active cases are on track. Reports delivered for 8, 4 pending scheduling."
- This kind of proactive communication is what differentiates a preferred imaging partner from a commodity vendor

### Churn Prediction

Combine signals to predict relationship risk:
- Declining referral volume
- Increasing communication friction
- Cases being redirected to other facilities
- Attorney office not responding to follow-ups

Flag at-risk relationships before they're lost.

## Value Proposition

"Your top 10 law firms probably generate 60%+ of your revenue. Do you know which ones are sending fewer patients this quarter? Do you know which ones pay fastest? An AI agent tracks every relationship continuously and tells you before you lose a key referral source."

## Revenue Model

- Monthly flat fee per active attorney relationship managed
- Or bundled with the Lien Portfolio Manager as a comprehensive AR intelligence package
- The cost of the agent is a fraction of the cost of losing one major referral source

## Leverages Existing Infrastructure

- Email classification already identifies attorney communications
- Lien agent already processes attorney-submitted documents
- MCP/RadFlow connection provides case and billing data
- FrontApp tracks all communication history with each contact

## What's New to Build

- Attorney/firm entity resolution (matching emails to firms)
- Referral tracking and trending analytics
- Scoring model
- Proactive outreach automation
- Relationship dashboard

## Build Effort: Medium

Entity resolution (mapping email addresses to firms) is the main technical challenge. Most data already flows through the existing system — this agent primarily adds cross-conversation analytics and proactive triggers.

## Priority: MEDIUM

High strategic value but harder to quantify ROI than direct revenue recovery. Best positioned as part of a broader AR intelligence package alongside the Lien Portfolio Manager.
