# Payer Contract Optimizer Agent

## The Problem

Imaging centers negotiate fee schedules with each insurance company. These contracts:

- Are dense legal documents with hundreds of CPT code-level rates
- Vary significantly between payers for the same study
- Are renegotiated every 1-3 years
- Most imaging centers have no idea whether they're being paid fairly relative to market rates
- Nobody tracks whether certain payers are actually profitable after accounting for denial rates, payment delays, and administrative costs
- Contract renegotiation is done with gut feel, not data

## The Solution: An AI Contract Intelligence Agent

### Contract Analysis

- Ingest every payer contract
- Extract fee schedules by CPT code
- Build a unified reimbursement database across all payers
- Flag anomalies: "Your rate for CPT 70553 (MRI brain with and without contrast) is $380 from Aetna but $520 from Cigna. The Aetna rate hasn't been updated since 2021."

### True Payer Profitability

"Aetna pays $450 for MRI lumbar but denies 22% of claims and takes 67 days to pay. Cigna pays $420 but denies 8% and pays in 31 days."

Calculate true profitability per payer:
```
Effective revenue = contracted rate x (1 - denial rate) x collection rate
                    - (cost of denied claim handling)
                    - (cost of capital for payment delay)
```

Cigna at $420 with 8% denial rate is often more profitable than Aetna at $450 with 22% denial rate.

### Benchmarking (Platform-Scale Opportunity)

If running across multiple imaging centers:
- "Your MRI reimbursement from Blue Cross is 12% below the market average for your region"
- Identify which contracts are below market and by how much
- This data is extraordinarily valuable during renegotiation

### Renegotiation Ammunition

When it's time to renegotiate a payer contract, the agent generates a complete brief:
- Current rates vs. market benchmarks
- Denial patterns and their cost impact
- Volume trends (leverage: "We send you X patients/year")
- Specific CPT codes where the center is underpaid
- Competitor rate intelligence (from aggregate data)
- Recommended target rates with supporting analysis

### Mix Optimization

"If you shifted 15% of your Blue Cross MRI volume to the evening shift (which currently runs at 40% capacity), you could take on 10% more Cigna patients at higher reimbursement. Net revenue impact: +$8,400/month."

Optimize which payers' patients fill which slots based on reimbursement rates and machine availability.

## Value Proposition

"When's the last time you renegotiated your Aetna contract? Do you know how your rates compare to the imaging center across town? An AI agent that continuously analyzes your payer mix and reimbursement rates can identify $100K+ in annual revenue improvement just from contract optimization."

## Revenue Model

- Annual fee for contract analysis and renegotiation support
- Percentage of identified revenue improvement
- Premium tier: aggregate benchmarking data (only available to platform customers)

## The Platform Data Moat

This is where the platform strategy becomes critical. A single imaging center's contract data is useful. Aggregate data across dozens of imaging centers is a **strategic asset**:

- Market-rate benchmarking by region, modality, and payer
- Payer behavior intelligence (which payers are tightening rates industry-wide)
- Negotiation playbooks based on what's worked for other centers

This data can't be assembled by any single imaging center. It requires the platform.

## Build Effort: Medium

Requires contract document ingestion (PDF/OCR), claims data integration, and financial modeling. The analytics layer is the core deliverable — less agent orchestration, more continuous intelligence.

## Priority: MEDIUM

High value but requires scale to build the benchmarking moat. Best deployed after establishing multiple imaging center clients through Prior Auth and Claims Intelligence. This is the product that locks in platform customers long-term.
