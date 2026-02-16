# Platform Strategy Overview

## The Vision

Transform from a single-client email tagging system into the AI operations platform for medical imaging — the intelligence layer between imaging centers, attorneys, and insurance payers.

## Current State

A production-grade email processing system for one medical imaging center (Precise Imaging) that:
- Classifies inbound emails into 30+ categories using hierarchical AI
- Routes tagged emails to specialized AI agents
- Auto-responds with context from backend systems (RadFlow via MCP)
- Handles lien processing, appointment inquiries, billing, records requests
- Has safety infrastructure (sandbox modes, sender verification, human review, audit traces)

## The Strategic Sequence

```
Phase 1: Deepen (Current Client)
   |
   v
Phase 2: Widen (Platform for Multiple Imaging Centers)
   |
   v
Phase 3: Expand (Adjacent Products - Insurance, Scheduling)
   |
   v
Phase 4: Flip (Sell to the Payer Side)
```

### Phase 1: Deepen (Months 1-6)
Maximize value with the current client by adding:

1. **Lien Portfolio Manager** — Proactive lien lifecycle management
2. **Revenue Cycle Intelligence** — Financial analytics and forecasting
3. **Attorney Relationship Agent** — Referral tracking and churn prevention
4. **EmailTag as MCP Server** — Foundation for agent-to-agent communication

Revenue model: Expand from flat fee to performance-based pricing tied to recovered revenue.

### Phase 2: Widen (Months 6-12)
Productize for multiple imaging centers:

1. **Multi-tenancy** — Tenant isolation across DB, queues, config, and agents
2. **CRM abstraction** — Support FrontApp + at least one more (Zendesk)
3. **Configurable classification trees** — Visual editor for category hierarchies
4. **Declarative agent routing** — Move from hardcoded if/elif to config-driven routing
5. **Self-service onboarding** — New imaging center can be set up without code changes

Revenue model: SaaS subscription per imaging center + performance fees.

### Phase 3: Expand (Months 9-18)
Add insurance-focused products:

1. **Prior Authorization Agent** — The $31B pain point
2. **Claims Intelligence Agent** — Denial prevention and recovery
3. **Scheduling Optimization Agent** — Machine utilization and no-show prediction
4. **Payer Contract Optimizer** — Reimbursement analysis and negotiation support

Revenue model: Per-transaction fees (per auth, per claim) + subscription + performance fees.

### Phase 4: Flip (Months 18-36)
Sell intelligence to payers:

1. **Utilization Review Automation** — AI-powered clinical review
2. **Network Intelligence** — Capacity and quality insights
3. **Fraud Detection** — Aggregate pattern analysis

Revenue model: Per-member-per-month or annual enterprise contracts.

## The Data Moat

Each phase builds data that makes the next phase possible:

- Phase 1 data (communication patterns, case outcomes) enables Phase 2 (benchmarking)
- Phase 2 data (aggregate provider behavior) enables Phase 3 (payer intelligence)
- Phase 3 data (claims + auth patterns) enables Phase 4 (payer-side products)

By Phase 4, the platform has visibility into both sides of every imaging transaction — a position no competitor can easily replicate.

## Architectural Evolution Required

| Component | Current | Platform Target |
|---|---|---|
| Category tree | Files in `app/prompts/rules/` | Per-tenant, UI-configurable |
| Agent routing | 900-line if/elif in `autorespond.py` | Declarative tag-to-agent config in DB |
| CRM integration | FrontApp only | Connector interface (Front, Zendesk, Gmail) |
| MCP connections | Single RadFlow server | Per-tenant MCP registry, multiple backends |
| Tenant model | None (single tenant) | Full tenant isolation |
| Agent implementations | Hardcoded Python per workflow | Agent builder with tool composition |
| Proactive triggers | None (purely reactive to email) | Time-based scheduling engine |
| Cross-conversation state | None | Entity timeline per patient/attorney/case |

## Competitive Position

The defensible advantages:

1. **Production-grade safety infrastructure** — Sandbox modes, sender verification, human review, processing traces. This is what makes businesses trust AI with real actions. Competitors would need to rebuild all of this.

2. **Domain expertise encoded in classification rules** — The hierarchical rule system captures deep knowledge of medical imaging operations. This isn't generic AI — it understands liens, prior auth, HIPAA, and PI case workflows.

3. **MCP as integration standard** — By building on MCP, the platform can connect to any system that exposes MCP tools. This is future-proof and extensible.

4. **Aggregate data** — With multiple imaging centers, the platform accumulates payer behavior intelligence, benchmarking data, and outcome patterns that no single center could generate alone.

## Key Risks

- **Regulatory** — HIPAA compliance for multi-tenant PHI handling is non-trivial
- **Sales cycle** — Healthcare organizations are slow to adopt new technology
- **Concentration** — Currently dependent on one client; if they churn before Phase 2, the business is at risk
- **Competition** — RCM (Revenue Cycle Management) is a crowded market; differentiation is through AI-native architecture
- **Payer tension** — Selling to both providers and payers creates inherent conflicts that must be carefully managed

## The Headline

**"From email tagging to the AI operating system for medical imaging."**

The email system was the foot in the door. The long-running agents are the real business. The platform is the endgame.
