# Implementation Plan — EmailTag ⇄ possibleos Firm-Intelligence Integration

> Builds against `FIRM_INTELLIGENCE_CONTRACT.md` (v0.1). Goal: EmailTag becomes
> the sole Front consumer and the firm-intelligence producer; possibleos drops
> its direct Front dependency and consumes the contract. Written as a delegation
> brief for Codex — each task is independently shippable and verifiable.

## Critical path (what the data told us)
The bottleneck is **not endpoints** — it's that EmailTag computes intelligence
but has persisted it for only 2–33% of firms. So the long pole is a **backfill**:
resolve websites + run enrichment across all 3,606 firms. Sequence accordingly.

```
EMAILTAG track (long pole)                         POSSIBLEOS track
E0 identity + website resolution (tiered)  ──┐
E1 enrichment backfill (behavioral/ICP/      │
   leadership across all firms)              │
E2 v2 contract endpoints                     ├──►  P1 consume contract (shadow vs front_sync)
E3 ingest-time website resolution (mandatory)│     P2 migrate FKs to firm_id via alias
E4 outcome-feedback intake (/outcomes)       │     P3 cut over; delete front_sync + FRONT key
                                             └──►  P4 send outcome feedback
```
possibleos runs **shadow** (consume contract alongside `front_sync`, diff) until
E1 coverage is adequate, then cuts over. No big-bang.

---

## EMAILTAG TRACK

### E0 — Canonical identity + tiered website resolution
- Add `canonical_domain()` per contract §2 (strip scheme/www/path, eTLD+1 via
  public-suffix list; exclude vanity `*.filevineapp.com`/`*.casepeer.com`/etc.
  and consumer domains).
- Add `firm_alias` table (alias_type, alias_value, firm_id, confidence, source).
  Backfill every existing `pif_id` (EmailTag + possibleos) and known domain/email
  domain as aliases.
- Implement tiered website resolution (contract §2): seed → HTTP verify →
  `web_search_preview` fallback (reuse `firm_researcher`) → human-review queue.
  Persist `canonical_website`, `website_status`, `website_source`, confidence.
- Dedup pass: cluster firms by canonical website; auto-merge high-confidence,
  queue low-confidence for review; merges recorded in `firm_alias` (reversible).
- **Verify:** ≥85% of firms reach `website_status=resolved`; dedupe report shows
  expected ~10% collapse; merges reversible from alias log.

### E1 — Enrichment backfill (THE long pole)
- Run existing analyzers across all 3,606 firms and **persist into `pif_info`**:
  `behavioral_data` (`email_analyzer`), `icp_score`/tier (`icp_scorer`),
  `leadership`/people (`signature_extractor` + role detection), inbox-split
  recency (referrals `inb_qfq9`, records `inb_rcld`).
- Idempotent, resumable, rate-aware batch job; emit coverage metrics.
- **Verify:** behavioral_data + ICP coverage rise from ~2%/1% toward firm base;
  spot-check N firms against raw conversations.

### E2 — v2 contract endpoints (`/api/v2/firm-intel`)
- `GET /firms/{firm_id}`, `GET /firms?updated_since=&cursor=` (delta),
  `GET /firms/resolve?website=|domain=|email=|legacy_pif_id=`,
  `GET /firms/{id}/people`, `GET /health`, `POST /outcomes`.
- Serialize the `firm_profile` (contract §4) incl. `vendor_stack`,
  inbox-split recency, neutral `warm_score`, provenance/freshness.
- Auth via existing `PIFSTATS_AUTH_TOKEN`; **non-PHI guarantee at the boundary.**
- **Verify:** `firm_profile` round-trips every field in contract §8 mapping;
  `updated_since` returns correct deltas.

### E3 — Ingest-time website resolution (mandatory, async)
- Chain the E0 resolver after `extract_pif_from_conversation` (webhooks.py:391).
  Run **once per firm** (skip if `website_status=resolved`), **async** (never
  inline in the 202 response).
- **Verify:** a new firm's first inbound email yields a resolved website without
  slowing the webhook.

### E4 — Outcome-feedback intake
- `POST /outcomes` (contract §6) → store; feed `icp_scorer` as supervised signal.
  Do **not** leak our-actions into the published facts layer.
- **Verify:** posting outcomes updates the scorer inputs, not the profile facts.

---

## POSSIBLEOS TRACK

### P1 — Consume the contract (shadow mode)
- New `firm_intel_client` calling `/api/v2/firm-intel` (reuse `PIFSTATS_AUTH_TOKEN`).
- Populate a local projection of `firm_profile`. Run **alongside** `front_sync`;
  diff warm_score/behavior/people; log deltas. No behavior change yet.
- **Verify:** diff report shows contract data ≥ parity with `front_firm_activity`
  on the consumed fields (contract §8).

### P2 — Migrate identity to firm_id via alias
- Resolve possibleos `pif_id`s → contract `firm_id` via `/resolve`. Key
  firms/contacts on `firm_id`; keep `pif_id` as alias for back-compat.
- **Verify:** every active firm/contact maps; no orphans introduced.

### P3 — Cut over and delete the Front dependency
- Switch selection/composer to read the contract projection.
- **Delete** `front_sync.py`, `FrontContactRow`, `FrontFirmActivityRow` population,
  and `FRONT_AUTH_TOKEN`. Keep policy/scoring (warm_score weighting, suppression,
  cooldowns) — fed by contract facts.
- **Verify:** a dry-run daily lead-gen run selects + composes with no Front access;
  `git grep FRONT_AUTH_TOKEN` is empty; behavioral pivot still fires.

### P4 — Outcome feedback
- Post contacted/replied/booked/qualified/won/lost to `POST /outcomes`.
- **Verify:** outcomes appear in EmailTag; loop closed.

---

## Cross-cutting
- **Cutover gate:** P3 only after E1 coverage ≥ parity (shadow diff clean).
- **Reversibility:** alias log + retained raw + shadow mode make every step
  reversible.
- **Repo conventions:** EmailTag — Celery tasks + Alembic migration + tests.
  possibleos — CLI parity (`CLAUDE.md` golden rule), decision-log entry, prompt
  protocol if any prompt changes. Co-Authored-By on commits.

## Open confirmations
- Public-suffix lib choice (EmailTag).
- Per-firm `web_search` budget cap for E0 backfill (~hundreds of firms).
- `firm_id` UUID space: reuse EmailTag `pif_info.id` as `firm_id`, or mint new.
</content>
