# Firm Merge — Production Runbook

How to run the non-destructive duplicate-merge (`scripts/firm_merge.py`, task
E0b) against the production EmailTag database. This is an **operator-run, held
step** — explicit, reviewed, never automated.

See also: `docs/MIGRATION_PLAN.md` (E0b) and `docs/FIRM_INTELLIGENCE_CONTRACT.md`
§2 (identity, "merge not delete").

## Deploy shape
EmailTag prod runs via docker-compose (`emailtag-web`, `emailtag-research-worker`,
…). The merge CLI uses the app's `SessionLocal`, so it acts on whatever DB the
prod environment points at. Run it **on the prod deploy host, inside the
`emailtag-web` container** (it has the code, env, and prod DB access).

## What the merge does (recap)
- Keyed on canonical website. Picks a **survivor** per duplicate cluster, unions
  the duplicates' data (emails, conversation_ids, leadership), records each merged
  id as a `legacy_pif_id` alias → survivor, and **soft-merges** losers
  (`merge_status='merged'`, `merged_into=<survivor>`). **Never hard-deletes.**
- **Guards:** junk/shared domains (e.g. `google.com`, mail vendors) and
  dissimilar-name clusters are routed to a **review queue**, not auto-merged.
- **Excludes** the ~632 no-derivable-website firms (they need website resolution
  first). The merge is **re-runnable** — run again after website resolution to
  catch their duplicates.

## Procedure

### 0. Back up (reversible, but snapshot anyway)
```bash
docker compose exec emailtag-web pg_dump "$DATABASE_URL" \
  -t pif_info -t firm_alias -t firm_merge_audit > firm_merge_backup_$(date +%F).sql
```

### 1. Deploy code + apply migration
Adds `merged_into` / `merge_status` / `merged_at` / `merged_from` columns and the
`firm_merge_audit` table.
```bash
git pull
docker compose exec emailtag-web alembic upgrade head
docker compose exec emailtag-web alembic current   # expect 0b91c2d3e4f5
```

### 2. Dry-run (zero writes — safe to run anytime)
Reads prod, prints survivors / losers / conflicts / review-flagged clusters, then
rolls back. This is the eyeball-before-apply step.
```bash
docker compose exec emailtag-web python scripts/firm_merge.py
```
Expect on the order of ~654 clusters, ~1,102 rows collapsing, junk clusters
routed to review.

### 3. Apply (the only writing command — double-gated)
```bash
docker compose exec emailtag-web python scripts/firm_merge.py --apply --yes
```

### 4. Verify
```bash
docker compose exec emailtag-web psql "$DATABASE_URL" \
  -c "SELECT merge_status, count(*) FROM pif_info GROUP BY 1;" \
  -c "SELECT count(*) FROM firm_merge_audit;"
```
Spot-check one merged firm: emails/conversation_ids unioned into the survivor,
`legacy_pif_id` aliases present.

### 5. Undo (if a cluster looks wrong)
Reverse from the audit record (`undo_firm_merge_task` / the audit id): restores
the soft-merged rows and removes the merge aliases.

## Safety notes
- **Only `--apply --yes` writes.** The dry-run is read-only and rolls back.
- Merge is reversible (audit + undo) and re-runnable (incremental).
- After the merge, the base is ~1,872 unique firms → run E1 enrichment on that
  clean set (no wasted work on duplicates).
