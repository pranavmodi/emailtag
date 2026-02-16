# Revenue Cycle Intelligence Agent

## The Problem

Imaging center financial managers make decisions about millions in receivables based on:
- Spreadsheets that are weeks old
- Manual reports from the billing department
- Gut feel about which cases will pay and which won't
- Reactive discovery of problems (missed filing deadlines, write-offs, underpayments)

They lack real-time, comprehensive financial intelligence across their entire revenue cycle.

## The Solution: A Continuous Financial Intelligence Agent

### Cash Flow Forecasting

"Based on case ages, attorney payment patterns, and settlement cycle analysis, expected cash inflows over the next 90 days are $X."

Inputs:
- All outstanding liens with age and attorney
- Historical payment timing by attorney/firm
- Insurance claims pipeline with expected payment dates
- Settlement probability modeling by case characteristics

Outputs:
- 30/60/90 day cash flow projections
- Confidence intervals (best case, expected, worst case)
- Monthly variance analysis (projected vs. actual)

### Bad Debt Early Warning

"These 15 cases have characteristics matching historical write-offs:"
- Old case age (>24 months)
- Unresponsive attorney (no communication in 6+ months)
- Patient not returning calls
- Multiple reschedules/no-shows before scan
- Attorney firm has high historical write-off rate

"Recommended action: escalate to collections now rather than waiting 6 more months when recovery probability drops below 10%."

### Negotiation Intelligence

When an attorney offers to settle a $5,000 lien for $3,000, the agent provides context:

"This attorney's firm has settled 12 previous cases with us:
- Average opening offer: 60% of billed amount
- Average final settlement: 78% of billed amount
- This opening offer ($3,000 / 60%) is consistent with their pattern
- Counter-offer recommendation: $4,200 (84% — slightly above their average, achievable based on case strength)
- Expected final settlement: $3,900 (78%)"

This turns every negotiation from a guessing game into a data-driven conversation.

### Procedure Profitability Analysis

"MRI lumbar referred by PI attorneys has a net collection rate of 68%. CT head from the same source has 82%. MRI brain from insurance patients has 94%."

Factor in:
- Billed amount
- Collection rate by payer type
- Denial/appeal costs
- Machine time and operational cost
- Staff time per study type

This tells the imaging center which studies and which payer channels are actually most profitable — often not what they assume.

### Aging Analysis with Actionable Intelligence

Not just "here's your AR aging report" but:
- "These 23 cases in the 90-120 day bucket are at risk of crossing payer-specific filing deadlines"
- "These 8 liens in the 12-18 month bucket have a 70% probability of full recovery if you act this week, but that drops to 30% if you wait another quarter"
- "Your 0-30 day AR is healthy but your 180+ day AR grew 15% this quarter — here's why"

## Value Proposition

"You're making financial decisions about millions in outstanding receivables based on static reports. An AI agent gives you a live financial picture, predicts problems before they happen, and tells you exactly where to focus your team's time for maximum recovery."

## Key Dashboards

1. **Portfolio Health** — Total outstanding by payer type, age distribution, risk score
2. **Cash Flow Forecast** — Projected inflows with confidence bands
3. **At-Risk Cases** — Cases flagged for intervention with recommended actions
4. **Payer Performance** — Denial rates, payment speed, effective reimbursement by payer
5. **Negotiation Tracker** — Active negotiations with AI-recommended positions

## Revenue Model

- Monthly subscription (positioned against the cost of a financial analyst: $60-80K/year)
- Premium tier: real-time alerts and automated interventions
- The agent costs less than one FTE but provides analysis that would require an entire finance team

## Build Effort: Medium

Most underlying data already flows through existing systems (RadFlow via MCP, FrontApp communications, email classification). The new work is the analytics/modeling layer and the dashboard. Less agent orchestration, more continuous intelligence.

## Priority: MEDIUM-HIGH

Natural extension of the Lien Portfolio Manager. Can be built incrementally — start with the aging analysis and cash flow forecast, add negotiation intelligence and predictive analytics over time. Strong upsell to existing client.
