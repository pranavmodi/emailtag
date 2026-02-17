# Strategic Conversation Context

## Date: February 15, 2026

## Summary

A strategic brainstorming session exploring how to evolve the EmailTag product (AI-powered email classification and autorespond system for Precise Imaging) into a broader platform and business.

---

## Thread 1: Product to Platform

### Core Insight
EmailTag isn't really an email tagging system. It's an **AI-powered inbound communication processor that understands intent, fetches context from business systems, takes autonomous action, and responds.** That pattern is universal across service businesses.

### Three Layers of Value Identified

1. **Classification Engine** — Hierarchical, file-based rule system with traceable LLM-based tree walking. Well-architected, auditable, versionable. Most competitors use flat single-prompt classification.

2. **Agent Orchestration** — Tag-to-agent routing with sandbox/production modes, sender verification, no-action lists, human review escalation, MCP bridge to backend systems. This is the core platform capability.

3. **MCP Data Bridge** — PreciseMCP connects agents to RadFlow. The pattern (expose business systems as MCP tools for AI agents) is the right abstraction for any backend.

### What's Hardcoded That Shouldn't Be
- Category tree (files in `app/prompts/rules/`) → needs per-tenant UI editor
- Agent routing (900-line if/elif in `autorespond.py`) → needs declarative config in DB
- CRM integration (FrontApp only) → needs connector interface
- Internal domains (hardcoded list) → needs per-tenant config
- MCP server (single localhost:8001) → needs MCP registry per tenant
- Tenant context (none) → needs full multi-tenancy

### The Actual Platform Moat
The operational trust layer — sandbox modes, sender verification, human review escalation, processing traces, no-action lists, infinite-loop detection. This is what makes businesses trust AI with real actions. Anyone can call GPT-4o. Not everyone has production-grade safety infrastructure.

### Three Highest-Leverage Moves
1. Abstract the CRM layer (CRMConnector interface, FrontApp becomes one implementation)
2. Make agent routing declarative (config table, not if/elif blocks)
3. Make classification trees tenant-configurable (visual tree builder UI)

---

## Thread 2: AI-Agent-First Design

### Core Insight
The system is already agentic but agents are **stateless, reactive, single-email**. The opportunity is making them **stateful, proactive, cross-conversation**.

### Three Tiers of AI-Agent Usage

**Tier 1: AI agents as consumers** (highest immediate value)
- Expose EmailTag itself as an MCP server
- Attorney AI agents submit liens via MCP instead of emailing PDFs
- Email becomes the human fallback, not the primary channel
- Every email represents structured intent forced into unstructured format — remove that translation

**Tier 2: AI agents as operators** (transforms operations)
- AI supervisor agent monitors classification accuracy, manages escalation dynamically, tunes templates based on outcomes
- Cross-conversation awareness: "Patient X has 4 open conversations that should be consolidated"
- Proactive follow-up: "72 hours since bill balance response, no reply — trigger follow-up"
- The settings API already exists — expose as tools for a supervisor agent

**Tier 3: AI agents as primary communicators** (most transformative)
- Both sides increasingly have AI — agent-to-agent through email is absurd
- Detect AI senders, offer channel upgrade to MCP
- Agent-to-agent protocols for medical imaging operations

### Key Advantages
- Volume without linearity (thousands of conversations with cross-conversation awareness)
- Temporal awareness (perfect tracking of every open thread and its age)
- Pattern detection at scale (trends no human would notice across thousands of emails)
- Self-improvement loops (continuous eval, A/B testing templates, measuring outcomes)

### Key Risks
- Accountability gap (who's responsible when AI adjusts rules and something goes wrong?)
- Adversarial dynamics (gaming classification once it's known AI runs the inbox)
- HIPAA for AI-to-AI communication involving PHI
- Debugging AI managing AI (configuration cascade failures)

---

## Thread 3: Medical Imaging Upsell — Long-Running Agents

### Core Business Insight
Precise Imaging's biggest problem isn't email. It's **revenue cycle management for personal injury cases**. Cases take 2-5 years to settle. Millions sit in outstanding liens with nobody actively managing them. The email system handles ~10% of the work (inbound communications). The other 90% is everything that should happen between emails but doesn't.

### Proposed Agents (by priority)
1. **Lien Portfolio Manager** — Continuous monitoring of every outstanding lien, stale case detection, automated escalation sequences, attorney-level intelligence, portfolio valuation
2. **Revenue Cycle Intelligence** — Cash flow forecasting, bad debt early warning, negotiation intelligence, procedure profitability analysis
3. **Attorney Relationship Agent** — Referral volume monitoring, firm scoring, payment pattern analysis, churn prediction
4. **Scheduling Optimization** — No-show prediction, waitlist management, capacity balancing, proactive coordination

### Pricing Insight
The email system is a cost center (saves staff time). Long-running agents are **revenue-generating and revenue-protecting**. Price on performance: % of recovered revenue, not flat SaaS fees.

---

## Thread 4: Insurance/Payer Opportunities

### The Big Insight
The email system and lien agents are AR tools — collecting money already owed. The payer/insurance side influences whether money is owed, how much, and how fast it arrives.

### Proposed Products (by priority)

1. **Prior Authorization Agent** (HIGHEST priority)
   - $31 billion industry pain point
   - Same architecture as email agents
   - Per-auth fee ($15-30) vs. current $40-60 staff cost
   - Every imaging center in the country has this problem

2. **Claims Intelligence Agent** (HIGH)
   - Pre-submission denial prevention
   - Denial pattern learning across payers
   - Automated appeals
   - Underpayment detection
   - Performance-based pricing on recovered revenue

3. **Payer Contract Optimizer** (MEDIUM)
   - True payer profitability analysis
   - Benchmarking (requires platform scale)
   - Renegotiation ammunition

4. **Payer-Side Products** (LONG-TERM, 18-36 months)
   - Utilization review automation (sell TO insurance companies)
   - Fraud/abuse detection (aggregate data from platform)
   - Network optimization intelligence

### The Data Moat
Each imaging center added to the platform accumulates aggregate payer behavior intelligence. Denial patterns, payment timing, clinical documentation that works — this data compounds and creates a network effect no single imaging center can replicate.

### Strategic Sequence
Phase 1 (Months 1-6): Deepen with current client (lien portfolio, revenue intelligence)
Phase 2 (Months 6-12): Widen to multiple imaging centers (multi-tenancy, CRM abstraction)
Phase 3 (Months 9-18): Expand to insurance products (prior auth, claims)
Phase 4 (Months 18-36): Flip to payer-side products

---

## Thread 5: Go-To-Market & Credibility (Possible Minds)

### Website Assessment (getpossibleminds.com)
- Professional design, good case study numbers, solid methodology messaging
- Critical gaps: zero search presence, no human/team page, anonymous case studies, 2 blog posts in 18 months, no compliance markers, no low-commitment engagement options

### Open Questions (Need Answers for GTM Playbook)
- Founder background and story
- Team size and composition
- Client situation (is Precise Imaging the only client?)
- Can either case study client be named?
- How was the first client acquired?
- Revenue/runway situation
- Target buyer persona (specific role and org size)
- Competitive landscape awareness
- Hours/week available for BD
- What outreach has been tried and what happened?

### Preliminary Recommendations
- Immediate: Add team page, push to name a case study client, start weekly LinkedIn
- Short-term: Write pain-point-targeted blog posts, create free assessment offer, join healthcare IT communities (HIMSS, RBMA)
- Medium-term: Speaking opportunities, vendor partnerships (RadFlow, FrontApp), content engine, pilot program

---

## Files Created

All detailed writeups saved to `/home/fret/work/emailtag/ideas/`:

| File | Topic | Priority |
|---|---|---|
| 01-prior-auth-agent.md | Prior Authorization Automation | HIGHEST |
| 02-claims-intelligence-agent.md | Claims Denial Prevention & Recovery | HIGH |
| 03-lien-portfolio-manager-agent.md | Proactive Lien Lifecycle Management | HIGH |
| 04-scheduling-optimization-agent.md | Machine Utilization & No-Show Prediction | MEDIUM-HIGH |
| 05-attorney-relationship-agent.md | Referral Tracking & Churn Prevention | MEDIUM |
| 06-payer-contract-optimizer.md | Reimbursement Analysis & Benchmarking | MEDIUM |
| 07-emailtag-as-mcp-server.md | Agent-to-Agent Communication Layer | HIGH |
| 08-payer-side-products.md | Selling TO Insurance Companies | LONG-TERM |
| 09-revenue-cycle-intelligence-agent.md | Financial Analytics & Forecasting | MEDIUM-HIGH |
| 10-platform-strategy-overview.md | Overall Platform Sequencing | — |
| 11-go-to-market-credibility-assessment.md | Website & GTM Analysis | — |
