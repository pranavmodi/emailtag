# Building a Firms Dashboard Against the EmailTag Backend

An implementation note for building a standalone frontend (equivalent to
`/pifstats/firms`) in a **separate repo** that talks directly to the EmailTag
FastAPI backend. Everything you need — auth, endpoints, data shapes, UI
behaviour, and the integration gotchas — is here.

---

## 1. Architecture

```
┌────────────────────────┐        HTTPS + cookie          ┌───────────────────────┐
│  Your new frontend      │  ───────────────────────────▶ │  EmailTag FastAPI      │
│  (any stack: React/Vue) │  ◀───────────────────────────  │  /api/v1/pif-info/*    │
│  credentials: include   │        JSON                    │  Postgres (pif_info)   │
└────────────────────────┘                                └───────────────────────┘
```

- The backend is a FastAPI app. All firm data lives in the `pif_info` table and
  is served under `/api/v1/pif-info/*`.
- Auth is a **signed session cookie** (not a bearer token). See §3.
- There is **no GraphQL** — plain REST + JSON.

### Base URL
- API prefix: **`/api/v1`** (`settings.API_V1_PREFIX`).
- The backend serves HTTPS (uvicorn with TLS) on its configured port (the
  existing frontend uses `http://localhost:8444` in dev via
  `NEXT_PUBLIC_API_BASE_URL`). Point your client at
  `${API_BASE_URL}/api/v1/...`.

---

## 2. The data model (`pif_info`)

One row = one firm/entity. Full field list (also what the export returns):

| Field | Type | Notes |
|---|---|---|
| `id` | uuid (string) | primary key = the `firm_id` |
| `firm_name` | string | |
| `entity_type` | string | see labels in §7; default `pi_law_firm` |
| `website`, `canonical_website` | string \| null | canonical = registrable domain |
| `website_status` | string \| null | `resolved` / `pending` / null |
| `website_source` | string \| null | `web_search` / `human` / … |
| `website_confidence` | number \| null | 0.0–1.0 |
| `website_candidate` | string \| null | pending review candidate |
| `emails`, `phones`, `addresses` | string[] | |
| `fax` | string \| null | |
| `contacts` | `PifContact[]` | from email extraction |
| `conversation_ids` | string[] | Front conversation IDs |
| `extraction_notes` | string \| null | |
| `leadership` | `LeadershipMember[]` \| null | from research |
| `staff` | `StaffMember[]` \| null | from staff research |
| `research_data` | `ResearchData` \| null | practice areas, firm size, etc. |
| `research_status` | string \| null | `completed`/`queued`/`in_progress`/`failed`/null |
| `staff_research_status` | string \| null | same value set |
| `last_researched_at` | ISO datetime \| null | |
| `behavioral_data` | `BehavioralData` \| null | email-behaviour analysis |
| `icp_score` | int \| null | 0–100 |
| `icp_tier` | string \| null | `A` (≥75) / `B` (≥50) / `C` (≥25) / `D` (<25) |
| `score_breakdown` | `ScoreBreakdown` \| null | per-signal scoring |
| `icp_scored_at` | ISO datetime \| null | |
| `vendor_stack` | `VendorStackEntry[]` \| null | practice-mgmt vendors; **null = none detected** |
| `merge_status` | string \| null | `active` / `merged` (soft-merged duplicate) |
| `created_at`, `updated_at` | ISO datetime | |

**Merged rows:** duplicates are soft-merged (`merge_status = 'merged'`) rather
than deleted. The list endpoint hides them by default (`active_only=true`).

---

## 3. Authentication (READ THIS FIRST — the main integration gotcha)

Auth is a **signed cookie**, not a header token.

### Flow
1. `POST /api/v1/pifstats-auth/login` with JSON `{ "username": "...", "password": "..." }`.
   - Default dev creds: username `admin`, password `topsecret`
     (password is hard-coded in `pifstats_auth.py`; the signing secret is
     `PIFSTATS_AUTH_SECRET` env, default `emailtag-pifstats-admin-auth`).
   - On success the response **sets an HttpOnly cookie** `pifstats_session`
     (HMAC-SHA256 signed, 24h TTL) and returns `{ authenticated: true, username }`.
2. Every subsequent request must send that cookie → use **`credentials: "include"`**
   on every `fetch`.
3. `GET /api/v1/pifstats-auth/check` → `200 { authenticated: true }` if the
   cookie is valid, `401` otherwise. Use it to gate your app / redirect to login.
4. `POST /api/v1/pifstats-auth/logout` clears the cookie.

Any `/pif-info/*` request without a valid cookie returns **`401`
`{"detail":"PIFStats authentication required"}`** (the whole router is gated by
`require_pifstats_auth`).

### Cookie attributes (these dictate where you can host the frontend)
The cookie is set with: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.

- **`Secure`** → the cookie is only sent over **HTTPS** (browsers exempt
  `localhost`). Your frontend and API calls must be HTTPS in any non-local env.
- **`SameSite=Lax`** → the cookie is sent on **same-site** requests. "Same site"
  = same registrable domain (eTLD+1); **subdomains and ports don't break it**.
  - ✅ `app.example.com` → `api.example.com` : same-site, cookie sent on fetch.
  - ✅ `localhost:3001` → `localhost:8444` : same-site (localhost), works in dev.
  - ❌ `dashboard.com` → `emailtag-api.net` : **cross-site**; `SameSite=Lax`
    will **not** send the cookie on a programmatic `fetch`. Auth will fail.
- **`HttpOnly`** → JS cannot read the cookie; you never touch it directly, the
  browser attaches it automatically when `credentials: "include"` is set.

**If your new frontend must live on a different registrable domain than the
API**, you have to either (a) change the backend cookie to `SameSite=None;
Secure` (in `pifstats_auth.py::set_pifstats_cookie`), or (b) reverse-proxy the
API under the frontend's domain so requests are same-origin, or (c) add a
bearer-token auth path. Option (b) (proxy) is the least invasive.

### CORS
The backend runs `CORSMiddleware(allow_origins=["*"], allow_credentials=True,
allow_methods=["*"], allow_headers=["*"])`. Starlette echoes the caller's
`Origin` back for credentialed requests, so cross-origin XHR is permitted at the
CORS layer — the **cookie SameSite/Secure rules above are the real constraint**,
not CORS.

---

## 4. Endpoint reference (`/api/v1/pif-info`)

### List firms — `GET /api/v1/pif-info/`
Returns `PifInfoListResponse`. Query params (all optional):

| Param | Values | Meaning |
|---|---|---|
| `search` | string | matches firm name / email / website |
| `page` | int ≥1 (default 1) | |
| `page_size` | 1–100 (default 20) | |
| `sort_by` | `conversation_count` \| `firm_name` \| `updated_at` (default) | |
| `research_status` | `completed`/`pending`/`queued`/`in_progress`/`failed` | exact match |
| `icp_tier` | `A`/`B`/`C`/`D` | |
| `entity_type` | see §7 keys | |
| `recently_researched` | int (days) | researched within last N days |
| `website_presence` | `any`/`has`/`missing`/`resolved`/`unresolved` | |
| `research_presence` | `any`/`completed`/`missing`/`queued_or_running`/`failed` | |
| `staff_presence` | same as research_presence | |
| `behavior_presence` | `any`/`has`/`missing` | |
| `icp_presence` | `any`/`has`/`missing` | |
| `vendor_presence` | `any`/`has`/`missing` | **null vendor_stack = missing** |
| `active_only` | bool (default `true`) | hide soft-merged duplicates |

### Get one firm — `GET /api/v1/pif-info/{id}` → `PifInfoResponse`

### Export
- All firms: `GET /api/v1/pif-info/export?format=json|csv&include_merged=false`
  — **streamed**. `json` = lossless nested array; `csv` = flat table with nested
  blobs JSON-encoded into cells. `Content-Disposition: attachment`.
- One firm: `GET /api/v1/pif-info/{id}/export?format=json|csv`.

### People search — `GET /api/v1/pif-info/people`
Params: `title`, `name`, `role_category`, `source` (`leadership`/`staff`/`all`),
`page`, `page_size`. Returns `PeopleSearchResponse` (flattened people across
firms).

### Per-firm actions (all POST; all dispatch async Celery tasks)
| Endpoint | Effect | Returns |
|---|---|---|
| `POST /{id}/enrich-all` | full pipeline chain (see §5) | `ResearchStartResponse` (task_id) |
| `POST /{id}/research` | firm research only | `ResearchStartResponse` |
| `POST /{id}/research-staff` | staff research only | `ResearchStartResponse` |
| `POST /{id}/detect-vendors` | vendor stack (3 tiers), no `research_status` change | `ResearchStartResponse` |
| `POST /{id}/analyze-behavior` | behaviour + ICP | (behavior response) |

### Task status polling
- `GET /api/v1/pif-info/research-status/{task_id}` → `ResearchStatusResponse`
- `GET /api/v1/pif-info/enrich-all/status/{task_id}` → `FullEnrichmentStatusResponse`
- `detect-vendors` has **no status endpoint** — instead poll the firm via
  `GET /{id}` and watch `updated_at` change (reliable even when zero vendors are
  found, since the row is still touched).

---

## 5. The full-enrichment workflow (`enrich-all`)

`POST /{id}/enrich-all` kicks off a Celery **chain**, executed in order:

```
1. website resolution
2. vendor stack detection      ← runs early so it survives later failures
3. firm research (leadership, practice areas, firm size, …)
4. leadership email history
5. staff research
6. behaviour analysis
7. signature extraction
8. ICP scoring
```

- Steps are sequential and mostly independent; a soft failure in one (returns
  a `{status: failed}` dict) does **not** abort the chain.
- To reflect progress in the UI, poll `GET /{id}` every few seconds and derive
  step states from the fields: `website_status`, `research_status`,
  `staff_research_status`, `behavioral_data` present, `icp_score` present,
  `vendor_stack` present, `research_data.leadership_email_history` present.
- Each research step is an LLM + web-search call (tens of seconds each); a full
  chain can take a few minutes.

---

## 6. TypeScript types (copy these verbatim)

```ts
export interface PifContact { name: string; title: string; email: string; phone: string; extension: string; }

export interface LeadershipMember {
  name: string; title: string;
  email: string | null; phone: string | null; linkedin: string | null;
  bio: string | null; image_url: string | null;
  education?: string[]; experience?: string[]; skills?: string[];
  certifications?: string[]; publications?: string[]; cases_handled?: string[]; bar_admissions?: string[];
}

export interface StaffMember {
  name: string; title: string;
  role_category: string; // intake_specialist|case_manager|paralegal|office_manager|billing_coordinator|medical_records|other
  email: string | null; phone: string | null; linkedin: string | null; bio: string | null;
}

export interface LeadershipEmailEntry {
  name: string; title: string; email: string; total_emails: number;
  first_contact: string | null; last_contact: string | null;
  tag_distribution: Record<string, number>; recent_subjects: string[]; matched_by: string;
}

export interface ResearchData {
  practice_areas: string[]; founded_year: string | null; firm_size: string | null;
  office_locations: string[]; notable_cases: string[]; awards_recognition: string[];
  bar_associations: string[]; social_media: Record<string, string>;
  additional_info: string | null; sources: string[];
  leadership_email_history?: LeadershipEmailEntry[];
}

export interface BehavioralData {
  total_email_count: number; monthly_email_volume: number[]; // [3 months oldest first]
  last_contact_date: string | null; days_since_last_contact: number | null;
  topic_distribution: Record<string, number>; primary_pain_point: string | null;
  sender_roles: Record<string, number>; contact_profiles?: Record<string, Record<string, unknown>>;
  peak_contact_days: string[]; after_hours_ratio: number; analyzed_at: string;
}

export interface ScoreBreakdown {
  email_volume_score: number; email_volume_reason: string;
  recency_score: number; recency_reason: string;
  pain_signals_score: number; pain_signals_reason: string;
  firm_size_score: number; firm_size_reason: string;
  completeness_score: number; completeness_reason: string;
  total: number; scored_at: string | null;
}

export interface VendorStackEntry {
  vendor: string;      // canonical lowercase, e.g. "filevine", "clio"
  source: string;      // "email_domain" | "inbox_content" | "job_posting" | "website" | ...
  confidence?: string; // "high" | "medium" | "low"
  known?: boolean;     // false = newly discovered vendor not in the curated list
  evidence?: string;
}

export interface PifInfoResponse {
  id: string; firm_name: string; entity_type: string;
  website: string | null; canonical_website: string | null;
  website_status: string | null; website_source: string | null; website_confidence: number | null;
  emails: string[]; phones: string[]; fax: string | null; addresses: string[];
  contacts: PifContact[]; conversation_ids: string[]; extraction_notes: string | null;
  leadership: LeadershipMember[] | null; research_data: ResearchData | null;
  research_status: string | null; last_researched_at: string | null;
  staff: StaffMember[] | null; staff_research_status: string | null;
  behavioral_data: BehavioralData | null;
  icp_score: number | null; icp_tier: string | null;
  score_breakdown: ScoreBreakdown | null; icp_scored_at: string | null;
  vendor_stack: VendorStackEntry[] | null;
  created_at: string; updated_at: string;
}

export interface PifInfoListResponse { items: PifInfoResponse[]; total: number; page: number; page_size: number; total_pages: number; }
export interface ResearchStartResponse { pif_id: string; firm_name: string; task_id: string; status: string; message: string; }
export interface FullEnrichmentStatusResponse { task_id: string; status: string; message: string; pif_id?: string | null; firm_name?: string | null; result?: Record<string, unknown> | null; }
```

---

## 7. Entity type labels

```ts
export const ENTITY_TYPE_LABELS: Record<string, string> = {
  pi_law_firm: "PI Law Firm",
  medical_referring: "Medical Referring",
  medical_facility: "Medical Facility",
  insurance: "Insurance",
  funding: "Funding",
  collections: "Collections",
  legal_other: "Legal (Other)",
  administrative: "Administrative",
  patient_adjacent: "Patient Adjacent",
};
```

---

## 8. UI behaviour spec (what `/pifstats/firms` does)

Reproduce these interactions:

**Login gate** — on load call `/pifstats-auth/check`; if `401`, show a login
form posting to `/pifstats-auth/login`, then re-check.

**Filter bar** (each control maps 1:1 to a list query param in §4):
- Search box (`search`), Website (`website_presence`), Research
  (`research_presence`), Staff (`staff_presence`), Behavior
  (`behavior_presence`), ICP (`icp_presence`), Vendors (`vendor_presence`),
  Entity type (`entity_type`), Sort (`sort_by`), "Active only" toggle
  (`active_only`), and a "Clear filters" button.
- Changing any filter resets to page 1 and refetches.

**Table** — paginated (page_size 25 is what the current UI uses), columns:
firm name, entity type, website, conversations count, ICP tier/score, research
status. Prev/Next pagination using `total_pages`.

**Expandable detail row** — clicking a firm expands a panel showing:
- Header actions: **Run full enrichment** (POST `enrich-all`, then poll status),
  **Export JSON / CSV** (per-firm export links), **Open website**.
- Contact data (emails/phones/addresses), Research status grid
  (research/staff/last-researched/ICP), Front conversation IDs.
- **Vendor Stack** section (chips of `vendor` + `source` + `confidence`; amber
  "new" badge when `known === false`) with a **Detect vendors** button (POST
  `detect-vendors`, then poll `GET /{id}` on `updated_at`).
- People sections: Leadership, Staff, Extracted Contacts.
- Raw JSON viewers for `research_data` and `behavioral_data`.

**Bulk export** — header buttons "Export all → JSON / CSV" hitting
`/pif-info/export?format=…` and triggering a browser download.

### Download helper (works with the cookie auth)
```ts
async function downloadFile(path: string, fallbackName: string) {
  const res = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Export failed ${res.status}`);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = cd.match(/filename="?([^"]+)"?/)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click();
  a.remove(); URL.revokeObjectURL(url);
}
```

### Minimal fetch client
```ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8444";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",                       // REQUIRED — sends the cookie
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (res.status === 401) throw new Error("unauthenticated"); // redirect to login
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.status === 204 ? ({} as T) : res.json();
}
```

---

## 9. ICP scoring reference
`icp_score` is 0–100 (deterministic, no LLM). Tiers: **A ≥75, B 50–74,
C 25–49, D <25**. `score_breakdown` explains the per-signal contribution
(email volume, recency, pain signals, firm size, completeness).

## 10. Vendor stack reference
Detection is three tiers merged & deduped (authority: `email_domain` >
`inbox_content` > web). Open-vocabulary: unknown vendors are kept with
`known:false`. **`vendor_stack === null` means no vendors detected** (not "not
run") — the filter treats null as "missing".

---

## 11. Gotchas checklist
- [ ] Every request uses `credentials: "include"`.
- [ ] Frontend + API are **same registrable domain** (or you changed the cookie
      to `SameSite=None; Secure`, or proxy the API). Otherwise cookie auth fails.
- [ ] HTTPS everywhere in non-local envs (cookie is `Secure`).
- [ ] Handle `401` globally → route to login.
- [ ] `vendor_stack`, `leadership`, `staff`, `research_data`, `behavioral_data`
      can all be `null` — guard every access.
- [ ] Long-running actions are async: dispatch → poll, never block on the POST.
- [ ] Bulk export is streamed and can be large (~2,400 firms) — download as a
      blob, don't buffer as text in state.
- [ ] Default creds/secret are placeholders — set `PIFSTATS_AUTH_SECRET` (and
      change the password in `pifstats_auth.py`) before exposing publicly.
```
