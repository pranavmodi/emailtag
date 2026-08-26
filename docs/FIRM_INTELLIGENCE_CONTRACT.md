# Firm Intelligence Contract (v2 — implemented)

> **The single interface between EmailTag (the refinery) and possibleos (the
> engine).** EmailTag publishes firm intelligence as a versioned, non-PHI data
> product; possibleos and every future Possible Minds tool (aiscan, aiaudit,
> Ghost Lead Test, the browser extension) consume it. This document is the
> keystone: both repos build backward from it.

Status: **v2 endpoints implemented + deployed (2026-07-05). Token auth is live.**
Owner of the contract: EmailTag (producer). Primary consumer: possibleos.
Companion design notes:
`possibleos/docs/product/` co-design discussion.

---

## 1. Principles (non-negotiable)

1. **Facts vs policy.** EmailTag publishes *facts about firms* (identity, people,
   behavior, vendors) + a *neutral* ICP score. possibleos owns *policy*
   (selection weighting, suppression, cadence, composition). EmailTag never
   decides who gets contacted.
2. **PHI boundary = system boundary.** Raw email / patient data never crosses.
   The contract carries only derived, safe intelligence. EmailTag is the egress
   point and guarantees non-PHI output.
3. **Raw is sacred; refined is re-derivable.** EmailTag retains raw extractions
   immutably; the published profile is a *versioned projection* of raw that can
   be recomputed with better models without re-fetching Front.
4. **Extraction identity is resolved once, at the source.** EmailTag owns raw
   PIF extraction and extraction-level deduplication. Possible OS owns
   canonical-domain web research and every derived field after extraction.
   identity (website-keyed). Consumers never re-resolve; they map their local
   ids via the alias table.
5. **Every field carries provenance, freshness, and confidence.** Consumers must
   be able to reason about staleness and trust, not just read bare values.
6. **Contract-first and versioned.** Schema changes are additive within a major
   version; breaking changes bump the version.

---

## 2. Identity model

### Canonical key
- **Identity/dedup key = canonical website URL** (registrable domain, eTLD+1).
- **Storage PK = a stable surrogate `firm_id` (UUID).** The canonical website is
  a UNIQUE natural key on the firm. FKs point at `firm_id`, so a rebrand is a
  one-row website update, not a cascade.

### Canonicalization rules (`canonical_domain(url|email)`)
1. lowercase; strip scheme, `www.`, path, query, fragment, trailing slash.
2. reduce to registrable domain via the public-suffix list
   (`mail.smithlaw.com` → `smithlaw.com`).
3. **Vendor/portal domains are NOT identity** — `*.filevineapp.com`,
   `*.casepeer.com`, `*.litify.com`, imaging/EMR portals (`simonmed.com`, etc.)
   → emit a **vendor/tech signal** + a "resolve real website" task; never a key.
4. **Consumer domains** (gmail/yahoo/outlook/icloud…) → never a key.
5. **No website yet** → deterministic surrogate key + `website_status="pending"`
   and a website-resolution task (below) to find the real site.

### Website resolution (tiered, mandatory at first sighting)

The website is a first-class asset, not just an identity key — the freeware
tools (aiscan/aiaudit/intake-teardown), the browser extension, and
firm_researcher all act on it. Every firm must converge to a **resolved,
verified** website. Resolution is tiered so search is only the residual path:

1. **Seed** from any known domain (extracted `firm_website`, else email domain).
2. **Verify** it resolves to the firm's real marketing site (HTTP reachable,
   not a vanity/portal/parked page, name matches). ~85% confirm here cheaply.
3. **Web search fallback** (`web_search_preview`, already used by
   `firm_researcher`): for firms with no usable domain (consumer email,
   vanity-only, missing) or where verify fails — search
   `"<firm name>" <city> personal injury` and pick the official site.
4. **Human review** for no-result / ambiguous (networks, multiple sites).

Each firm carries `website_status` (resolved | pending | none) +
`website_source` (email_verified | web_search | human) + confidence. Resolution
is **idempotent and run once per firm** — cached after success; re-run only on
failure or staleness. When the verified website's registrable domain **differs**
from the email domain, the **website is canonical** and the email domain is kept
as an **alias**.

**Trigger points (both):**
- **Ingest (mandatory, async):** chained after `extract_pif_from_conversation`
  on first sighting of a firm — guaranteed to run, but once per firm and never
  inline in the webhook response.
- **Backfill (one-time):** resolve the existing ~3,606 firms.

### Alias table (the dedup spine + backward compat)
`firm_alias(alias_type, alias_value, firm_id, confidence, source, created_at)`
- `alias_type ∈ {legacy_pif_id, domain, alt_domain, email_domain, vanity_domain, firm_name_fuzzy}`
- Every old `pif_id` (EmailTag and possibleos) is recorded as a `legacy_pif_id`
  alias, so existing references keep resolving.
- Merges are recorded here, never destructive; reversible.

---

## 3. Layered store (inside EmailTag)

```
RAW (immutable, append-only)        raw signatures, extracted entities, sender
                                    records, conversation refs, domains observed
   │ resolve
IDENTITY (firm + firm_alias)        canonical website key, surrogate firm_id
   │ refine (versioned, recomputable)
REFINED (firm_profile)              people, behavior, vendor, ICP — published
```

Existing `pif_info` research becomes **refined v1**, linked to the raw it came
from. No current data is discarded.

---

## 4. The `firm_profile` object (the published product)

```jsonc
{
  "firm_id": "uuid",                       // stable surrogate PK
  "canonical_website": "smithlaw.com",     // identity key (null if pending)
  "website_status": "resolved|pending|none",
  "firm_name": "Smith Injury Law",
  "aliases": {                             // for consumer mapping
    "legacy_pif_ids": ["…"], "domains": ["smithlaw.com","smith-law.com"],
    "vanity_domains": ["smithlaw.filevineapp.com"]
  },

  "identity": {                            // firmographics
    "metro": "los-angeles", "city": "...", "state": "CA",
    "size_hint": "5-30", "icp_tier": "A|B|C|D",
    "case_mix": {...}, "value_tier": "...", "volume_proxy": 0
  },

  "people": [                              // decision-makers + staff
    { "person_id": "uuid", "name": "...", "title": "...",
      "email": "...", "phone": "...", "linkedin": "...", "bio": "...",
      "publications": [...], "cases_handled": [...],
      "bar_admissions": [...],
      "persona": "owner|managing_partner|coo_ops|intake|records|...",
      "is_decision_maker": true,
      "freshness": { "last_seen_at": "...", "source": "signature|sender" },
      "confidence": 0.0 }
  ],

  "relationship": {                        // Precise relationship intelligence
    "warm_score_neutral": 0,               // EmailTag's neutral score (not policy)
    "trajectory": "heating|steady|cooling",
    "last_referral_at": "...",             // inbox inb_qfq9
    "last_records_at": "...",              // inbox inb_rcld
    "last_seen_at": "...",
    "monthly_email_volume": [0,0,0],
    "total_email_count": 0,
    "inbox_breakdown": { "inb_qfq9": {...}, "inb_rcld": {...} },
    "autorespond_seen": true               // has seen Precise autoresponders
  },

  "behavior": {                            // operational tells (non-PHI aggregates)
    "primary_pain_point": "intake|records|liens|status|...",
    "topic_distribution": { ... },
    "sender_roles": { "intake": 12, "records": 5, ... },
    "after_hours_ratio": 0.0,
    "peak_contact_days": ["Mon","Fri"]
  },

  "vendor_stack": {                        // NEW — the vendor-intel gap
    "case_mgmt": "filevine|litify|casepeer|smartadvocate|merus|null",
    "other": { "lien_funder": "...", "imaging": "...", "marketing": "..." },
    "evidence": [ { "signal": "domain:smithlaw.filevineapp.com", "confidence": 0.9 } ]
  },

  "icp": { "score": 0, "tier": "A|B|C|D", "score_breakdown": { ... } },

  "research": {                            // firm_researcher output (refined)
    "summary": "...", "practice_areas": [...], "sources": [...],
    "founded_year": 1998, "firm_size": "5-30",
    "office_locations": [...], "notable_cases": [...],
    "awards_recognition": [...], "bar_associations": [...],
    "social_media": { ... },
    "research_status": "done|pending|none", "last_researched_at": "..."
  },

  "provenance": {                          // contract-wide metadata
    "profile_version": 1,
    "refined_at": "...", "raw_observed_through": "...",
    "freshness_age_hours": 0.0, "source": "emailtag"
  }
}
```

Research detail is passed through from `pif_info.research_data` when present:
`founded_year`, `firm_size`, `office_locations`, `notable_cases`,
`awards_recognition`, `bar_associations`, and `social_media`. People detail is
passed through from leadership/staff records when present: `linkedin`, `bio`,
`publications`, `cases_handled`, and `bar_admissions`. If dedicated
`identity.metro` / `city` / `state` fields are absent, the first
`office_locations` entry is used as a string passthrough source.

---

## 5. Events / moments (push — phase 2)

EmailTag emits firm moments when a firm materially changes, and accepts external
moments from approved consumers so outreach can be timing-aware:

```jsonc
{ "event": "new_referral|became_warm|first_interaction|went_quiet|new_decision_maker|vendor_detected|report_viewed|report_engaged",
  "firm_id": "uuid", "canonical_website": "...", "occurred_at": "...",
  "detail": { ... } }
```

LexVisibility report engagement moments arrive via `POST /events/external`
with source `external:lexvisibility` and event types `report_viewed` and
`report_engaged`.

Phase 1 may skip push and rely on `updated_since` polling.

---

## 6. Outcome feedback (possibleos → EmailTag — closes the loop)

possibleos reports GTM outcomes back so EmailTag's ICP scorer learns:

```jsonc
{ "firm_id": "uuid", "event": "contacted|replied|booked|qualified|won|lost|unsubscribed",
  "occurred_at": "...", "channel": "email|call", "detail": { ... } }
```

EmailTag treats these as supervised signal for ICP/segment scoring. It does
**not** make them part of the published profile's policy (no leakage of our
moves into the facts layer); they only sharpen the neutral score.

---

## 7. Endpoints (pull)

Base: `https://emailprocessing.mediflow360.com/api/v2/firm-intel`
Auth: existing `PIFSTATS_AUTH_TOKEN` (header). Versioned under `/v2`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/extractions?updated_since=<ts>&cursor=` | Non-PHI PIF extraction delta for Possible OS; excludes free-form extraction notes, canonical research, leadership, staff, vendors, scoring, and job postings |
| GET | `/firms/{firm_id}` | full `firm_profile` |
| GET | `/firms?updated_since=<ts>&cursor=` | **delta sync** (replaces watermark poll) |
| POST | `/firms` | create or resolve a candidate firm from consumer-discovered identity |
| GET | `/firms/resolve?website=|domain=|email=|legacy_pif_id=` | alias → `firm_id` |
| GET | `/firms/{firm_id}/people` | people only |
| GET | `/events/catalog` | supported event vocabulary |
| POST | `/events/external` | external firm signal ingest |
| GET | `/health` | coverage + freshness (replaces `front_status`) |
| POST | `/outcomes` | possibleos → outcome feedback (§6) |

`/extractions` is the production ownership boundary. `/firms` remains a
read-only compatibility surface during rollout. Downstream mutation routes are
disabled by default with `PIF_DOWNSTREAM_ENRICHMENT_ENABLED=false`; Possible OS
must execute and persist that work locally.

Extraction cursors are opaque keyset cursors ordered by `(updated_at, id)`.
Consumers must return them unchanged and must not interpret them as offsets.

Phase additions beyond today's `pif-info`: **inbox-split recency**,
**vendor_stack**, **`updated_since` delta**, **neutral warm score**, **resolve**.

---

## 8. possibleos consumed-field → contract mapping (lossless proof)

| possibleos uses today (`front_firm_activity`) | Contract field |
|---|---|
| `warm_score` | `relationship.warm_score_neutral` (+ possibleos reweights) |
| `behavioral_json.after_hours_ratio` | `behavior.after_hours_ratio` |
| `behavioral_json.primary_pain_point` | `behavior.primary_pain_point` |
| `behavioral_json.top_sender_roles` | `behavior.sender_roles` |
| `inbox_breakdown` | `relationship.inbox_breakdown` |
| `last_referral_at` / `last_records_at` / `last_seen_at` | `relationship.*` |
| `contact_count` | `relationship.total_email_count` |
| `tech_signals.case_mgmt` | `vendor_stack.case_mgmt` |
| decision-maker contacts (`firm_contacts`) | `people[]` |
| firmographics (`firm_competitive_features`) | `identity.*` |

Every field possibleos reads has a home → migration is provably lossless.

---

## 9. Authoritative numbers (measured 2026-06-24, live `pif_info` API)

- **Total firms: 3,606** (3,204 `pi_law_firm`). possibleos mirror (3,598) is current.
- **research_status=completed: 779 (22%)**; pending/queued: 0 (research idle).
- **ICP tier assigned: 36 firms**; **behavioral_data present: ~2%**;
  leadership present: ~23%.
- **Website field present: ~33%, BUT derivable canonical domain (website OR
  email): ~85%.** → website-as-PK is viable; ~15% need web-search resolution.
- Dedup: ~10% of a 500-firm sample share a canonical domain (name variants).

**The gating finding:** EmailTag *computes* behavioral/ICP/leadership/website
intelligence (the code exists: `email_analyzer`, `icp_scorer`,
`signature_extractor`, `firm_researcher` web search) but has only **persisted it
for 2–33% of firms**. The capability exists as code, not as data. Therefore the
critical-path work is an **enrichment + website-resolution backfill across all
3,606 firms**, not endpoint plumbing. See `MIGRATION_PLAN.md`.

Confirmed design choices: Phase 1 = pull only (push deferred); cutover =
shadow/parallel against possibleos `front_sync` then flip; website = canonical
identity, email domain = alias.
</content>
