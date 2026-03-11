# Lien Negotiation Insights — Implementation Plan

> Build a structured negotiation intelligence system on top of Precise Imaging's email inbox, capturing both sides of every lien negotiation to surface patterns, predict outcomes, and inform strategy.

---

## Table of Contents

1. [Strategic Context](#strategic-context)
2. [Current System Capabilities](#current-system-capabilities)
3. [The Gap](#the-gap)
4. [Data Schema](#data-schema)
5. [Phase 1: Data Model + Real-Time Extraction](#phase-1-data-model--real-time-extraction)
6. [Phase 2: Historical Mining](#phase-2-historical-mining)
7. [Phase 3: Analytics Dashboard + Insights](#phase-3-analytics-dashboard--insights)
8. [Implementation Priorities](#implementation-priorities)
9. [Key Technical Decisions](#key-technical-decisions)
10. [Background: The Opportunity](#background-the-opportunity)
11. [Background: What Drives Accept/Counter/Litigate Decisions](#background-what-drives-acceptcounterlitigate-decisions)
12. [Background: Full Data Category Reference](#background-full-data-category-reference)

---

## Strategic Context

### The Unfair Advantage

Precise Imaging's inbox receives hundreds of emails/day from PI law firms — negotiating lien reductions, disputing bills, requesting case updates. This gives Possible Minds visibility into **both sides** of every negotiation:

- **What law firms request** and at what amounts
- **What Precise Imaging counters or accepts**
- **How many rounds** occur before resolution
- **Which arguments move the needle** and which don't
- **What the actual floor is** — the number PI won't go below
- **Which firms are aggressive** vs. which accept the first counter
- **Temporal patterns** — month-end, quarter-end, year-end acceptance behavior

Every other lien resolution company (Power Liens, Medfinancial) only sees one side. This dataset, once structured, becomes the only one in existence showing what medical providers actually accept.

### The Business Model

Lien resolution companies charge 20-35% of the reduction achieved. The intelligence from this system can:
1. **Immediately** help Precise Imaging's billing team negotiate more effectively
2. **Medium-term** power a lien resolution product for law firms (knowing the floor = knowing the optimal offer)
3. **Long-term** become a clearinghouse platform — serving both providers and firms, like title companies in real estate

---

## Current System Capabilities

### What Already Exists

| Capability | Location | Details |
|---|---|---|
| Email classification into Negotiations subcategories | `app/services/classification_service.py` | Tags: Bill Offer, Counter Offer Sent, Pending Approval |
| Case update tracking | `app/agents/case_updates_agent.py` | Drop Letter, Promise to send payment, Payment on way, etc. |
| Lien processing (upload, modification detection) | `app/agents/lien_agent.py` | PSL/ASL, Rad/Tech lien upload to RadFlow |
| Full conversation history via Front API | `app/services/frontapp_service.py` | `get_conversation_text()` returns all messages with metadata |
| Classification traces with LLM summaries | `app/models/classification_trace.py` | Every classification step logged with chosen_option, summary |
| PIF/law firm basic info | `pifstats/`, `app/api/api_v1/endpoints/pif_info.py` | Firm name, domain, email volume, ICP scores |
| Patient ID extraction + RadFlow integration | `app/agents/lien_agent.py` | MCP tools: `fetch_patient_info`, `get_patient_lien_bill_balance` |
| Batch conversation querying | `scripts/get_conversations_by_multiple_tags.py` | Fetch conversations by tag with pagination |
| Front search API | `pifstats/src/front_client.py` | `search_front_conversations()` full-text search |

### Relevant Email Categories (Leaf Tags)

```
Accounts Receivable
├── Billing
│   └── Bill or balance Request
├── Liens
│   ├── Missing Lien Request
│   ├── PSL (Patient Signed Lien)
│   │   ├── Rad Lien
│   │   ├── Tech Lien
│   │   └── Lien Modified
│   └── ASL (Attorney Signed Lien)
│       ├── Rad Lien
│       ├── Tech Lien
│       └── Lien Modified
├── Negotiations          ← PRIMARY TARGET
│   ├── Bill Offer
│   ├── Pending Approval
│   └── Counter Offer Sent
├── Case Updates          ← SECONDARY TARGET (settlement/payment signals)
│   ├── New Attorney
│   ├── Drop Letter
│   ├── Drop Pending
│   ├── Promise to send payment
│   ├── Waiting to clear liability
│   ├── Waiting on settlement check
│   ├── Sent payment but not received
│   ├── Refund Request
│   └── Payment on way
└── Collections
    ├── To send to collections
    ├── Attorney Non-Payment
    └── To Review
```

### Key Existing Infrastructure

- **Celery task pipeline**: Email receipt → OCR → classification → tagging → autorespond (agents). New extraction task slots in after tagging.
- **MCP tools**: RadFlow integration for patient/billing data lookup.
- **Database**: PostgreSQL with Alembic migrations. Current head: `c1d2e3f4a5b6`.
- **Frontend**: Next.js in `frontend/settings2/`. PIF intelligence page already exists as a template for the negotiations dashboard.
- **Front API**: Full read/write access — conversations, messages, tags, comments, search.

---

## The Gap

| What's Missing | Impact |
|---|---|
| No structured negotiation records | We tag "Bill Offer" but don't extract the dollar amount or track the offer/counter chain |
| No lien lifecycle tracking | We know a lien was uploaded but not: original billed amount, reduction requests received, counters sent, final accepted amount |
| No law firm negotiation behavior profiles | PIF has basic info but not: payment history, negotiation aggressiveness, relationship volume |
| No outcome data capture | The most valuable data point (what was actually accepted) isn't captured |
| No temporal/pattern analytics | No way to see quarter-end acceptance spikes, avg rounds to resolution, argument effectiveness |
| No conversation-to-negotiation linking | Multiple Front conversations can relate to the same negotiation (same patient + firm) |

---

## Data Schema

### negotiation_case

The core record representing one lien negotiation (one patient, one firm, one lien).

```python
class NegotiationCase(Base):
    __tablename__ = "negotiation_case"

    id = Column(UUID, primary_key=True, default=uuid4)

    # Linking
    front_conversation_ids = Column(ARRAY(String))  # Multiple threads possible
    patient_id = Column(String, index=True)          # RadFlow patient ID (PREXXXXX)
    firm_id = Column(UUID, ForeignKey("pif_info.id"), nullable=True)
    firm_name = Column(String, index=True)
    firm_domain = Column(String)

    # People
    attorney_name = Column(String)
    attorney_email = Column(String)
    sender_role = Column(String)  # attorney, paralegal, case_manager, lien_company
    lien_company_name = Column(String, nullable=True)

    # Injury / Case
    injury_type = Column(String)  # auto_accident, slip_and_fall, workers_comp, etc.
    body_parts = Column(JSONB)    # ["cervical_spine", "lumbar_spine", "knee"]
    case_settled = Column(Boolean, default=False)
    settlement_amount = Column(Numeric(12, 2), nullable=True)
    settlement_date = Column(Date, nullable=True)
    total_medical_bills = Column(Numeric(12, 2), nullable=True)  # All providers
    total_liens_all_providers = Column(Numeric(12, 2), nullable=True)

    # The Lien (Precise Imaging's side)
    lien_type = Column(String)          # PSL or ASL
    lien_subtype = Column(String)       # Rad or Tech
    original_billed_amount = Column(Numeric(12, 2))
    cpt_codes = Column(JSONB)           # [{"code": "70553", "description": "MRI Brain w/wo contrast"}]
    service_dates = Column(JSONB)       # ["2025-06-15", "2025-07-01"]
    num_procedures = Column(Integer)
    lien_filed_date = Column(Date, nullable=True)
    lien_state = Column(String)         # State where lien filed
    lien_perfection_quality = Column(String)  # good, defective, unknown
    amounts_already_collected = Column(Numeric(12, 2), default=0)

    # Negotiation Outcome
    case_status = Column(String, default="open")
    # Enum: open, negotiating, resolved, collections, written_off, abandoned
    resolution_type = Column(String, nullable=True)
    # Enum: accepted, counter_accepted, litigated, written_off, abandoned
    first_offer_amount = Column(Numeric(12, 2), nullable=True)
    first_offer_as_pct = Column(Numeric(5, 2), nullable=True)  # % of billed
    final_accepted_amount = Column(Numeric(12, 2), nullable=True)
    reduction_percentage = Column(Numeric(5, 2), nullable=True)
    total_rounds = Column(Integer, default=0)
    time_to_resolution_days = Column(Integer, nullable=True)
    who_moved_more = Column(String, nullable=True)  # firm, pi, even
    first_offer_accepted = Column(Boolean, nullable=True)
    payment_received = Column(Boolean, default=False)
    payment_received_date = Column(Date, nullable=True)
    payment_amount = Column(Numeric(12, 2), nullable=True)

    # Timestamps
    first_contact_date = Column(Date)
    last_activity_date = Column(Date)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    rounds = relationship("NegotiationRound", back_populates="case", order_by="NegotiationRound.round_number")
```

### negotiation_round

Each offer/counter in the negotiation.

```python
class NegotiationRound(Base):
    __tablename__ = "negotiation_round"

    id = Column(UUID, primary_key=True, default=uuid4)
    negotiation_case_id = Column(UUID, ForeignKey("negotiation_case.id"), index=True)

    # Message linking
    front_message_id = Column(String)
    front_conversation_id = Column(String)

    # Round details
    round_number = Column(Integer)
    direction = Column(String)      # inbound (firm→PI) or outbound (PI→firm)
    offer_amount = Column(Numeric(12, 2), nullable=True)
    offer_as_pct_of_billed = Column(Numeric(5, 2), nullable=True)

    # Argument analysis
    arguments_cited = Column(JSONB)
    # e.g. ["made_whole_doctrine", "state_statute_12345", "equity", "hardship",
    #        "lien_perfection_defect", "proportionality"]
    argument_quality_score = Column(Numeric(3, 1), nullable=True)  # 0-10, LLM-assessed
    specific_statutes_cited = Column(JSONB)   # ["Cal. Civ. Code § 3040"]
    specific_case_law_cited = Column(JSONB)   # ["US Airways v. McCutchen"]

    # Sender analysis
    sender_email = Column(String)
    sender_name = Column(String)
    sender_role = Column(String)    # attorney, paralegal, case_manager, lien_company
    tone = Column(String)           # professional, aggressive, deferential, threatening

    # Context
    new_info_introduced = Column(Boolean, default=False)
    new_info_description = Column(String, nullable=True)
    settlement_disclosed = Column(Boolean, default=False)
    settlement_amount_disclosed = Column(Numeric(12, 2), nullable=True)
    total_liens_disclosed = Column(Boolean, default=False)

    # Timing
    message_date = Column(DateTime)
    days_since_previous_round = Column(Integer, nullable=True)

    # Metadata
    extraction_confidence = Column(Numeric(3, 2))  # 0-1, how confident the LLM extraction was
    raw_message_snippet = Column(Text, nullable=True)  # Key excerpt for audit
    created_at = Column(DateTime, default=func.now())

    # Relationships
    case = relationship("NegotiationCase", back_populates="rounds")
```

### firm_negotiation_profile

Aggregated view of a firm's negotiation behavior (recomputed periodically).

```python
class FirmNegotiationProfile(Base):
    __tablename__ = "firm_negotiation_profile"

    id = Column(UUID, primary_key=True, default=uuid4)
    firm_name = Column(String, index=True)
    firm_domain = Column(String, unique=True)
    pif_info_id = Column(UUID, ForeignKey("pif_info.id"), nullable=True)

    # Volume metrics
    total_cases = Column(Integer, default=0)
    trailing_12mo_cases = Column(Integer, default=0)
    total_billed_amount = Column(Numeric(14, 2), default=0)
    total_collected_amount = Column(Numeric(14, 2), default=0)

    # Negotiation behavior
    avg_opening_offer_pct = Column(Numeric(5, 2))        # % of billed
    median_opening_offer_pct = Column(Numeric(5, 2))
    avg_final_settlement_pct = Column(Numeric(5, 2))      # % of billed
    median_final_settlement_pct = Column(Numeric(5, 2))
    avg_rounds_to_resolution = Column(Numeric(4, 1))
    avg_days_to_resolution = Column(Numeric(6, 1))
    first_offer_acceptance_rate = Column(Numeric(5, 2))   # % of cases where first offer accepted

    # Payment behavior
    payment_reliability_score = Column(Numeric(3, 1))     # 1-5 scale
    avg_days_to_payment = Column(Integer, nullable=True)  # After agreement
    has_defaulted = Column(Boolean, default=False)
    default_count = Column(Integer, default=0)

    # Tactics
    uses_lien_company = Column(Boolean, default=False)
    lien_company_name = Column(String, nullable=True)
    common_arguments = Column(JSONB)       # {"made_whole": 12, "equity": 8, "hardship": 3}
    has_threatened_litigation = Column(Boolean, default=False)
    litigation_threat_followed_through = Column(Boolean, default=False)

    # Derived scores
    relationship_value_score = Column(Numeric(5, 2))      # 0-100
    negotiation_difficulty_score = Column(Numeric(5, 2))   # 0-100 (higher = harder to deal with)

    # Timestamps
    last_case_date = Column(Date)
    profile_computed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

---

## Phase 1: Data Model + Real-Time Extraction

**Goal:** Start capturing structured negotiation data from every incoming email, beginning immediately.

### 1a. Database Migration

Create the three tables above via Alembic migration. Add indexes on:
- `negotiation_case.patient_id`
- `negotiation_case.firm_name`
- `negotiation_case.case_status`
- `negotiation_case.created_at`
- `negotiation_round.negotiation_case_id`
- `negotiation_round.message_date`
- `firm_negotiation_profile.firm_domain`

### 1b. Negotiation Extraction Agent

**Trigger:** After an email is classified under `Accounts Receivable → Negotiations` (Bill Offer, Counter Offer Sent, Pending Approval) or relevant `Case Updates` tags.

**Implementation pattern:** Same as existing agents (e.g., `case_updates_agent.py`). New file: `app/agents/negotiation_extraction_agent.py`.

**Extraction flow:**

```
1. Receive email + classification tag + conversation_id
2. Fetch full conversation thread via get_conversation_text()
3. Call GPT-4o with structured output schema:
   - Extract: offer_amount, arguments_cited, sender_role, tone,
     settlement_disclosed, settlement_amount, patient_id, firm_name
   - Assess: argument_quality_score, extraction_confidence
4. Look up existing negotiation_case by:
   - Same front_conversation_id, OR
   - Same patient_id + firm_domain combo
5. If no existing case → create negotiation_case
6. Create negotiation_round record
7. Update case: total_rounds++, last_activity_date, case_status
8. If resolution detected (acceptance language) → update outcome fields
```

**LLM prompt design:** The prompt needs to extract financial amounts from varied email formats:
- "We are offering $3,500 to resolve this lien"
- "Our client authorizes payment of 40% of the billed amount"
- "Please accept $2,100 in full satisfaction"
- "We will agree to reduce to $4,000 from the original $8,500"

Use GPT-4o with JSON structured output (same pattern as classification service).

### 1c. Lien-Side Data Enrichment

**When:** A lien is successfully uploaded via `lien_agent.py`.

**Addition to existing flow:** After successful RadFlow upload, call `get_patient_lien_bill_balance` MCP tool to get:
- Original billed amount
- CPT codes and service dates
- Any existing payment history

Create or update a `negotiation_case` record with the lien-side data. This ensures we have the billing baseline before any negotiation emails arrive.

### 1d. Celery Task Registration

New tasks in `app/tasks/negotiation_extraction.py`:
- `extract_negotiation_data_task(email_id)` — single email extraction
- `link_negotiation_to_case_task(negotiation_round_id)` — async case linking

Queue: `processing` (same as behavior analysis tasks).

### Files to Create/Modify

| File | Action |
|---|---|
| `app/models/negotiation.py` | **Create** — NegotiationCase, NegotiationRound, FirmNegotiationProfile models |
| `migrations/versions/xxxx_add_negotiation_tables.py` | **Create** — Alembic migration |
| `app/schemas/negotiation.py` | **Create** — Pydantic schemas for API + extraction |
| `app/agents/negotiation_extraction_agent.py` | **Create** — LLM extraction logic |
| `app/tasks/negotiation_extraction.py` | **Create** — Celery tasks |
| `app/crud/negotiation.py` | **Create** — CRUD operations |
| `app/tasks/email.py` | **Modify** — Add extraction task dispatch after Negotiations tagging |
| `app/agents/lien_agent.py` | **Modify** — Add negotiation_case creation on lien upload |

---

## Phase 2: Historical Mining

**Goal:** Build the initial dataset by processing historical negotiation emails from Front.

### 2a. Batch Conversation Fetcher

**Script:** `scripts/negotiation_historical_extraction.py`

**Flow:**
1. Query Front for all conversations tagged `Bill Offer`, `Counter Offer Sent`, `Pending Approval` using `get_conversations_by_multiple_tags.py` pattern
2. Also query `Case Updates` tags for settlement/payment signals
3. For each conversation:
   a. Fetch full message thread via `get_conversation_text()`
   b. Feed through same extraction LLM as Phase 1
   c. Create `negotiation_case` + `negotiation_round` records
4. Rate limit: Front API allows ~50 req/min. With backoff, estimate ~30 conversations/min
5. Log progress and errors for review

**Estimated volume:** Need to check how many conversations exist with these tags. Run:
```bash
# Count conversations by tag
python scripts/get_conversations_by_multiple_tags.py --tags "Bill Offer" --count-only
python scripts/get_conversations_by_multiple_tags.py --tags "Counter Offer Sent" --count-only
```

### 2b. RadFlow Billing Enrichment

For each historical `negotiation_case` with a `patient_id`:
1. Call RadFlow MCP tool `get_patient_lien_bill_balance` to get billing data
2. Fill in: `original_billed_amount`, `cpt_codes`, `service_dates`
3. Where available, pull payment data for **outcome tracking**

**Key question:** Does RadFlow store payment/write-off history? If so, we can determine `final_accepted_amount` and `payment_received` from RadFlow rather than email extraction alone. This is the most reliable outcome data source.

### 2c. Firm Profile Aggregation

**Script:** `scripts/build_firm_negotiation_profiles.py`

After historical cases are populated:
1. Group `negotiation_case` records by `firm_domain`
2. Compute aggregates: avg opening offer %, avg rounds, avg days, acceptance rate
3. Cross-reference with `pif_info` table for additional firm metadata
4. Populate `firm_negotiation_profile` records

**Scheduled refresh:** Add Celery beat task to recompute profiles nightly.

---

## Phase 3: Analytics Dashboard + Insights

**Goal:** Surface actionable intelligence through API endpoints and a frontend dashboard.

### 3a. API Endpoints

New router: `app/api/api_v1/endpoints/negotiations.py`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/negotiations/cases` | Paginated case list with filters (firm, status, date, amount) |
| `GET` | `/negotiations/cases/{id}` | Full case detail with all rounds |
| `GET` | `/negotiations/cases/{id}/timeline` | Visual timeline data for round-by-round view |
| `PUT` | `/negotiations/cases/{id}` | Manual correction of extracted data |
| `GET` | `/negotiations/firms` | Firm list with negotiation metrics |
| `GET` | `/negotiations/firms/{id}` | Full firm negotiation profile |
| `GET` | `/negotiations/analytics/summary` | Overall KPIs: avg reduction %, avg rounds, resolution time |
| `GET` | `/negotiations/analytics/temporal` | Monthly/quarterly patterns (acceptance rates, amounts) |
| `GET` | `/negotiations/analytics/arguments` | Argument effectiveness ranking |
| `GET` | `/negotiations/analytics/firm-comparison` | Side-by-side firm comparison |
| `POST` | `/negotiations/predict/floor` | Given case params → predicted floor amount |
| `POST` | `/negotiations/predict/strategy` | Given case params → recommended counter + arguments |

### 3b. Frontend Dashboard

New page: `frontend/settings2/app/negotiations/page.tsx`

**Tabs:**

1. **Active Cases** — Table of open negotiations with: patient, firm, current offer, last activity, days open, status badge. Click to expand round-by-round timeline.

2. **Firm Intelligence** — Searchable list of firms with: total cases, avg reduction achieved, payment reliability, negotiation difficulty score. Click for detailed profile with historical pattern charts.

3. **Insights** — Charts and visualizations:
   - Reduction % distribution (histogram)
   - Avg accepted amount by lien age (line chart)
   - Acceptance rate by month/quarter (bar chart — reveals year-end patterns)
   - Argument effectiveness (ranked bar chart — which arguments correlate with bigger reductions)
   - Rounds-to-resolution distribution
   - Time-to-resolution distribution

4. **Predictions** (Phase 3 late) — Input form: enter case details (billed amount, firm, lien age, settlement amount) → get predicted floor, recommended counter, suggested arguments.

### 3c. Derived Scores (Computed Nightly)

**Celery beat task:** `compute_negotiation_scores_task`

Scores per the strategic framework:

| Score | Inputs | Range |
|---|---|---|
| **Lienholder Position Strength** | Lien perfection quality + state law + lien age + amount vs settlement | 0-100 |
| **Law Firm Pressure** | Days since settlement + Medicare involvement + tone urgency + payment history | 0-100 |
| **Relationship Value** | Trailing 12mo volume + payment history + years of relationship | 0-100 |
| **Argument Strength** | Specificity of statutes + case law citations + knowledge of lien defects | 0-100 |
| **Expected Floor** | Regression on all historical outcomes given case inputs | Dollar amount |

---

## Implementation Priorities

| Priority | Task | Effort | Dependencies |
|---|---|---|---|
| **P0** | Database models + Alembic migration | 1 day | None |
| **P0** | Pydantic schemas + CRUD | 1 day | Models |
| **P0** | Negotiation extraction agent (real-time) | 2-3 days | Schemas, CRUD |
| **P0** | Wire extraction into email processing pipeline | 0.5 day | Agent |
| **P1** | Historical batch extraction script | 2 days | Agent, CRUD |
| **P1** | RadFlow billing enrichment (real-time + batch) | 1-2 days | Models |
| **P1** | Firm profile aggregation (script + Celery beat) | 1 day | Historical data |
| **P2** | Analytics API endpoints | 2 days | CRUD, data |
| **P2** | Manual correction API (PUT endpoint) | 0.5 day | CRUD |
| **P3** | Frontend dashboard (Active Cases + Firm Intel) | 3-4 days | API |
| **P3** | Frontend Insights tab (charts) | 2 days | API |
| **P3** | Predictive floor model | 3-5 days | Historical data (200+ resolved cases) |
| **P3** | Alerts (deviation from firm patterns) | 1 day | Firm profiles |

**Total estimated:** ~3-4 weeks for full implementation across all phases.

---

## Key Technical Decisions

### 1. Outcome Data Source

The `final_accepted_amount` is the most valuable field. Options:
- **Email extraction:** LLM detects acceptance language ("We agree to accept $X"). Reliable when explicit.
- **RadFlow payment data:** If RadFlow tracks actual payments received, this is ground truth. Need to verify: does `get_patient_lien_bill_balance` MCP tool return payment history?
- **Manual entry:** Billing team marks cases as resolved with final amount. Fallback for cases where neither source is clear.
- **Recommendation:** Use all three. RadFlow payments as primary truth, email extraction as secondary, manual as override.

### 2. Conversation Threading

A single negotiation can span multiple Front conversations (e.g., initial offer in one thread, counter in a new email). Linking strategy:
- **Primary key:** `patient_id` + `firm_domain` combo. If both match an existing case, link to it.
- **Secondary:** Same `front_conversation_id`. If a reply stays in-thread, auto-link.
- **Manual:** UI allows merging two cases that the system didn't auto-link.

### 3. LLM Model

- **Extraction agent:** GPT-4o (needs to understand financial amounts, legal arguments, tone — not a mini task)
- **Historical batch:** Same GPT-4o but can batch with higher token limits
- **Argument quality scoring:** GPT-4o (legal knowledge required)
- **NEVER use gpt-4** — always gpt-4o per project rules

### 4. When to Create vs. Update a Case

```
If email classified as Negotiations tag:
  1. Extract patient_id + firm from email
  2. Search negotiation_case WHERE patient_id = X AND firm_domain = Y AND case_status != 'resolved'
  3. If found → add negotiation_round to existing case
  4. If not found → create new negotiation_case + first round
  5. If patient_id missing → create case with conversation_id only, flag for enrichment
```

### 5. Privacy / Access Control

Negotiation data includes financial amounts and legal arguments. The analytics dashboard should:
- Use same auth as existing settings UI (currently simple local auth: user/user123)
- Consider role-based access if multiple teams will use it
- Never expose individual case data in aggregate views without authentication

### 6. Manual Override

The billing team must be able to correct LLM-extracted amounts. Requirements:
- Edit button on each case and round in the UI
- `PUT /negotiations/cases/{id}` endpoint
- Audit trail: store `manually_corrected: bool` and `corrected_by` fields
- Manual corrections should be flagged so they don't get overwritten by re-extraction

---

## Background: The Opportunity

### Why Lien Resolution Is the Best AI Opportunity in PI

| Task | Current Vendors | Pricing | AI Opportunity |
|---|---|---|---|
| Medical record retrieval | ChartSquad, Lexitas | $40-75/request | Retrieval + organization |
| Medical chronologies | EvenUp, Tavrn, Supio | $300-500/demand | AI drafting, competitive |
| **Lien resolution** | **Power Liens, Medfinancial** | **20-35% of reduction** | **Highest defensibility, least competed** |
| Intake / phone answering | Answering Legal, Smith.ai | Monthly sub | Commoditized |

Lien resolution ranks highest because:
- EvenUp doesn't do it
- Budget is performance-based (no sales resistance)
- Intelligence requirements are high (Medicare, ERISA, Medicaid, provider lien law)
- Possible Minds has the unique dual-sided data asset

### What Lien Resolution Involves

**Four phases:**

1. **Identification** — Find every entity with a right to reimbursement (health insurers, Medicare, Medicaid, workers' comp, hospital/provider liens, ERISA plans, litigation funders)
2. **Verification** — Request final lien amounts, verify charges relate to injury, audit for errors, confirm lien was properly perfected
3. **Negotiation** — The high-skill phase. Reduction strategies vary by lien type:
   - Medical provider liens: most negotiable, 30-50 cents on dollar typical
   - Health insurance subrogation: state anti-subrogation laws, 30-50% reductions
   - ERISA plans: hardest, federal preemption, limited equity arguments
   - Medicare: formal compromise process, automatic attorney fee reduction
   - Medicaid: state law governs, Ahlborn/Gallardo allocation arguments
   - Workers' comp: statutory, 25-40% typical reductions
4. **Documentation & Disbursement** — Written confirmation, formal releases, court approval where required, correct payment sequencing

**Timeline:** 30 days to 6+ months from settlement to disbursement.

---

## Background: What Drives Accept/Counter/Litigate Decisions

Understanding Precise Imaging's decision factors is the foundation of the analytical model:

**Lien Economics:**
- Original billed amount vs. actual cost of service
- Whether offer is above or below cost floor
- Age of receivable (older = more willing to discount)
- Whether case has actually settled (post-settlement = real money)

**Settlement Economics:**
- Total settlement vs. total liens (pressure when pie is small)
- PI's lien as share of total liens (proportionality)
- Whether client was made whole

**Law Firm Relationship:**
- Volume of cases sent (relationship premium — high-volume firms likely get better rates)
- Payment history
- Local vs. out-of-market firms

**Negotiation Quality:**
- Who sent the request (attorney vs. paralegal vs. lien company)
- Quality of legal arguments (generic template vs. specific statute)
- Whether firm demonstrated knowledge of lien perfection quality
- Tone of correspondence

**Internal Business Factors:**
- Month-end / quarter-end cash flow pressure
- Year-end write-off appetite (November-December)
- Billing department capacity
- Collections attorney relationship

**Legal Risk Assessment:**
- State law environment
- Quality of lien perfection
- Whether attorney cited specific legal defects
- Actual litigation threshold (almost certainly higher than implied)

---

## Background: Full Data Category Reference

### Category 1: The Lien
- Original billed amount, CPT codes, service dates, number of procedures
- Lien filing date, state, perfection quality (statutory deadline, notice, form)
- Amounts already collected, internal cost of services, Medicare/commercial benchmark rates

### Category 2: The Case
- Injury type (auto/slip-fall/workers-comp/med-mal/premises/product)
- Injury severity (soft tissue/fracture/surgery/permanent/catastrophic/fatality)
- Body parts, imaging findings (normal/abnormal/significantly abnormal)
- Treatment timeline: injury date, first/last PI visit, total duration, gaps
- Liability clarity, defendant type, defense insurance company, policy limits
- Settlement: amount, date, pre/post-suit, allocation breakdown, total bills/liens

### Category 3: The Law Firm
- Firm size, primary practice, geographic market
- Relationship duration, lifetime + trailing 12mo case volume, payment history
- Specific attorney experience, reputation signals
- Who negotiates (attorney personally vs. delegation to staff)

### Category 4: The Negotiation Process
- Each round: date, amount, arguments, time elapsed, who broke stalemate
- Communication: total emails, elapsed time, phone calls, formal vs. informal
- Resolution: who made final concession, triggering argument/document, payment timing

### Category 5: External Context
- Month/quarter of resolution, age of receivable
- State tort environment, anti-subrogation protections, court backlog
- Other lienholders' settlement status, Medicare involvement

### Category 6: Outcome Quality Signals
- Collection speed vs. average
- Write-off portion
- Relationship impact (more/fewer cases in following 6 months)
- Attorney involvement cost
- Whether agreed amount was actually paid

### Derived Variables
- **Lienholder Position Strength Score** — lien perfection + state law + age + amount vs settlement
- **Law Firm Pressure Score** — days since settlement + Medicare + tone + payment history
- **Relationship Value Score** — trailing 12mo volume + payment history + years
- **Made Whole Probability** — settlement vs. total damages
- **Argument Strength Score** — statute specificity + case law + lien knowledge
- **Expected Floor** — model prediction of minimum acceptable amount

### Key Questions the Dataset Can Answer
- What opening offer maximizes probability of immediate acceptance?
- What argument combination produces fastest resolution?
- At what lien age does the reservation price drop significantly?
- Which firms over-negotiate vs. reach optimal outcomes efficiently?
- What is the actual litigation threshold (amount + circumstances)?
- Do year-end / quarter-end patterns create predictable acceptance windows?
- What is the relationship premium worth in dollar terms?
