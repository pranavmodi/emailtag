# PIF (Personal Injury Firm) API Documentation

**Base URL:** `https://emailprocessing.mediflow360.com`

All PIF endpoints are unauthenticated and publicly accessible. CORS is configured to allow all origins.

---

## Table of Contents

- [Firm Lookup & Discovery](#firm-lookup--discovery)
- [Firm CRUD](#firm-crud)
- [People Search](#people-search)
- [Research](#research)
- [Behavior Analysis & ICP Scoring](#behavior-analysis--icp-scoring)
- [Outreach Generation](#outreach-generation)
- [Analytics](#analytics)
- [Batch Processing](#batch-processing)
- [Pipeline Management](#pipeline-management)
- [Data Models](#data-models)

---

## Firm Lookup & Discovery

### Search for Firms

**`POST /api/v1/pif-info/firm-lookup`**

Searches for firms across the local database and Front CRM conversations.

**Request Body:**
```json
{
  "firm_name": "string (optional)",
  "website": "string (optional)",
  "email": "string (optional)",
  "phone": "string (optional)",
  "contact_name": "string (optional)"
}
```

**Response:**
```json
{
  "matching_firms": [PifInfoResponse],
  "conversations": [
    {
      "id": "string",
      "subject": "string",
      "snippet": "string",
      "date": "datetime",
      "source": "local | front"
    }
  ],
  "total_conversations": 0
}
```

---

### Create Firm from Lookup

**`POST /api/v1/pif-info/firm-lookup/create`**

Creates or updates a firm from lookup results. Optionally starts research immediately.

**Request Body:**
```json
{
  "firm_name": "string",
  "website": "string (optional)",
  "email": "string (optional)",
  "phone": "string (optional)",
  "contact_name": "string (optional)",
  "selected_conversation_ids": ["string"],
  "start_research": true
}
```

**Response:**
```json
{
  "pif": PifInfoResponse,
  "is_new": true,
  "task_id": "string (optional, if start_research=true)",
  "message": "string"
}
```

---

## Firm CRUD

### List All Firms

**`GET /api/v1/pif-info/`**

Paginated list of all firms with search and sorting.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `search` | string | — | Search term (matches firm name, email, website) |
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (1-100) |
| `sort_by` | string | — | Sort order: `conversation_count`, `firm_name`, `updated_at` |

**Response:**
```json
{
  "items": [PifInfoResponse],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "total_pages": 0
}
```

---

### Get Single Firm

**`GET /api/v1/pif-info/{pif_id}`**

Returns the complete firm record with all nested data: contacts, leadership, staff, research data, behavioral data, ICP scores.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:** `PifInfoResponse` (see [Data Models](#data-models))

---

### Create Firm

**`POST /api/v1/pif-info/`**

**Request Body:**
```json
{
  "firm_name": "string",
  "website": "string (optional)",
  "emails": ["string"],
  "phones": ["string"],
  "fax": "string (optional)",
  "addresses": ["string"],
  "contacts": [
    {
      "name": "string",
      "title": "string",
      "email": "string",
      "phone": "string",
      "extension": "string"
    }
  ],
  "conversation_ids": ["string"]
}
```

**Response:** `PifInfoResponse`

**Validation:** Returns 400 if a firm with the same website already exists.

---

### Update Firm

**`PUT /api/v1/pif-info/{pif_id}`**

All fields are optional. Only provided fields are updated.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Request Body:** Same fields as Create, all optional.

**Response:** `PifInfoResponse`

---

### Delete Firm

**`DELETE /api/v1/pif-info/{pif_id}`**

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:**
```json
{
  "status": "success",
  "message": "Deleted firm: Firm Name"
}
```

---

## People Search

### Search Across All Firms' Leadership & Staff

**`GET /api/v1/pif-info/people`**

Cross-firm search for people by title, name, role, or source.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | string | — | Search by title (e.g. "CMO", "intake") |
| `name` | string | — | Search by person name |
| `role_category` | string | — | Filter by role: `intake_specialist`, `case_manager`, `paralegal`, `office_manager`, `billing_coordinator`, `medical_records`, `other` |
| `source` | string | `all` | Filter source: `leadership`, `staff`, `all` |
| `page` | int | 1 | Page number |
| `page_size` | int | 50 | Items per page (1-200) |

**Response:**
```json
{
  "results": [
    {
      "name": "string",
      "title": "string",
      "email": "string",
      "phone": "string",
      "linkedin": "string",
      "bio": "string",
      "source": "leadership | staff",
      "role_category": "string",
      "firm_name": "string",
      "firm_id": "uuid",
      "firm_website": "string"
    }
  ],
  "total": 0,
  "page": 1,
  "page_size": 50,
  "total_pages": 0
}
```

---

## Research

### Start Leadership Research

**`POST /api/v1/pif-info/{pif_id}/research`**

Queues an async Celery task that researches firm leadership, practice areas, and LinkedIn profiles.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:**
```json
{
  "pif_id": "uuid",
  "firm_name": "string",
  "task_id": "string",
  "status": "queued",
  "message": "Research task queued. Poll /research-status/{task_id}"
}
```

---

### Start Staff Research

**`POST /api/v1/pif-info/{pif_id}/research-staff`**

Queues an async Celery task that searches for operational staff: intake specialists, case managers, paralegals, office managers, billing coordinators, medical records staff.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:** Same format as leadership research response.

---

### Poll Research Status

**`GET /api/v1/pif-info/research-status/{task_id}`**

Poll for research task completion (works for both leadership and staff research).

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `task_id` | string | Celery task ID returned from research endpoints |

**Response:**
```json
{
  "pif_id": "uuid",
  "firm_name": "string",
  "task_id": "string",
  "status": "queued | in_progress | completed | failed",
  "leadership": [LeadershipMember],
  "research_data": {
    "practice_areas": ["string"],
    "founded_year": 0,
    "firm_size": "string",
    "office_locations": ["string"],
    "notable_cases": ["string"],
    "awards": ["string"],
    "bar_associations": ["string"],
    "social_media": {},
    "sources": ["string"]
  },
  "message": "string"
}
```

`leadership` and `research_data` are only populated when `status` is `completed`.

---

## Behavior Analysis & ICP Scoring

### Analyze Firm Behavior

**`POST /api/v1/pif-info/{pif_id}/analyze-behavior`**

Queues an async task that fetches all emails from the firm's conversation IDs, classifies them by topic using gpt-4o-mini, and computes an ICP score.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:**
```json
{
  "pif_id": "uuid",
  "firm_name": "string",
  "task_id": "string",
  "status": "queued",
  "message": "string"
}
```

**Resulting behavioral_data (stored on firm record):**
```json
{
  "total_emails": 0,
  "monthly_volume": {"2025-01": 5, "2025-02": 3},
  "last_contact_date": "datetime",
  "topic_distribution": {"scheduling": 0.4, "billing": 0.2},
  "sender_roles": {"attorney": 5, "paralegal": 3},
  "peak_contact_days": ["Monday", "Wednesday"],
  "after_hours_ratio": 0.15
}
```

---

### Batch Analyze All Firms

**`POST /api/v1/pif-info/analyze-behavior/batch`**

Queues behavior analysis for ALL firms. Dispatches individual tasks per firm.

**Response:**
```json
{
  "task_id": "string",
  "message": "string",
  "total": 0
}
```

---

### Score a Single Firm

**`POST /api/v1/pif-info/{pif_id}/score`**

Runs deterministic ICP scoring synchronously (no LLM call). Requires `behavioral_data` to already be present on the firm record.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:**
```json
{
  "pif_id": "uuid",
  "firm_name": "string",
  "icp_score": 85,
  "icp_tier": "A",
  "score_breakdown": {
    "volume_score": 25,
    "recency_score": 20,
    "topic_diversity_score": 15,
    "engagement_score": 25
  }
}
```

**ICP Tiers:**
| Tier | Score Range |
|------|-------------|
| A | 75-100 |
| B | 50-74 |
| C | 25-49 |
| D | 0-24 |

---

### Batch Score All Firms

**`POST /api/v1/pif-info/score/batch`**

Re-scores all firms that have existing `behavioral_data`.

**Response:**
```json
{
  "task_id": "string",
  "message": "string",
  "total": 0
}
```

---

## Outreach Generation

### Generate Outreach Messages

**`POST /api/v1/pif-info/{pif_id}/generate-outreach`**

Generates personalized LinkedIn outreach messages for each leadership member. Requires leadership data (run research first).

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Request Body:**
```json
{
  "case_study_url": "string (optional)",
  "client_description": "string (optional)"
}
```

**Response:**
```json
{
  "pif_id": "uuid",
  "firm_name": "string",
  "messages": [
    {
      "leader_name": "string",
      "leader_title": "string",
      "shortPranav": "string",
      "shortNeha": "string",
      "longPranav": "string",
      "longNeha": "string",
      "subjectShortPranav": "string",
      "subjectShortNeha": "string",
      "subjectLongPranav": "string",
      "subjectLongNeha": "string"
    }
  ],
  "errors": ["string"]
}
```

Each leader gets 4 message variants (short/long x Pranav/Neha persona) with corresponding subject lines.

---

## Analytics

### Summary Analytics

**`GET /api/v1/pif-info/analytics/summary`**

Aggregate analytics across all tracked firms.

**Response:**
```json
{
  "total_firms_tracked": 0,
  "firms_by_tier": {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 0,
    "unscored": 0
  },
  "top_pain_points": [
    {"topic": "scheduling", "count": 45},
    {"topic": "billing", "count": 30}
  ],
  "avg_monthly_volume_by_tier": {
    "A": 12.5,
    "B": 6.3,
    "C": 2.1,
    "D": 0.5
  },
  "pipeline_funnel": {
    "not_started": 0,
    "sent": 0,
    "replied": 0,
    "meeting_booked": 0,
    "closed_won": 0,
    "closed_lost": 0
  },
  "firms_contacted_last_30_days": 0,
  "firms_needing_recontact": 0
}
```

`firms_needing_recontact`: Tier A/B firms with last contact > 60 days ago.

---

## Batch Processing

### Process a Day's Conversations

**`POST /api/v1/pif-info/process-day`**

Extracts firm info from all conversations on a given date.

**Request Body:**
```json
{
  "target_date": "2026-03-16"
}
```

**Response:**
```json
{
  "date": "2026-03-16",
  "total_conversations": 0,
  "processed": 0,
  "firms_found": 0,
  "firms_created": 0,
  "firms_updated": 0,
  "errors": ["string (first 10 errors)"]
}
```

---

### Extract Single Conversation

**`POST /api/v1/pif-info/extract-conversation/{conversation_id}`**

Extracts firm info from a single Front conversation.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `conversation_id` | string | Front conversation ID |

**Response:**
```json
{
  "conversation_id": "string",
  "extracted": true,
  "is_new_firm": true,
  "pif_id": "uuid",
  "firm_name": "string",
  "firm_info": {
    "emails": ["string"],
    "phones": ["string"],
    "contacts": [{}]
  }
}
```

---

### Get Conversations for a Date

**`GET /api/v1/pif-info/conversations/{date_str}`**

Returns all conversation IDs for a given date.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `date_str` | string | Date in YYYY-MM-DD format |

**Response:** `["conversation_id_1", "conversation_id_2", ...]`

---

## Pipeline Management

Outreach pipeline records track contact attempts with firms.

**Base path:** `/api/v1/pif-pipeline`

### Create Pipeline Record

**`POST /api/v1/pif-pipeline/`**

**Request Body:**
```json
{
  "pif_id": "uuid",
  "contact_name": "string (optional)",
  "contact_linkedin": "string (optional)",
  "contact_email": "string (optional)",
  "outreach_type": "linkedin_connection | linkedin_inmail | email | referral",
  "sender_persona": "pranav | neha (optional)",
  "status": "not_started",
  "message_variant": "shortPranav | shortNeha | longPranav | longNeha (optional)",
  "sent_at": "datetime (optional)",
  "replied_at": "datetime (optional)",
  "notes": "string (optional)"
}
```

**Response:** `PipelineRecordResponse`

**Validation:** Returns 404 if `pif_id` does not exist.

---

### List Pipeline Records for a Firm

**`GET /api/v1/pif-pipeline/by-firm/{pif_id}`**

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `pif_id` | UUID | Firm ID |

**Response:**
```json
{
  "items": [PipelineRecordResponse],
  "total": 0
}
```

Records are sorted by `created_at`.

---

### Get Single Pipeline Record

**`GET /api/v1/pif-pipeline/{record_id}`**

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `record_id` | UUID | Pipeline record ID |

**Response:** `PipelineRecordResponse`

---

### Update Pipeline Record

**`PUT /api/v1/pif-pipeline/{record_id}`**

All fields optional. Only provided fields are updated.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `record_id` | UUID | Pipeline record ID |

**Request Body:**
```json
{
  "contact_name": "string (optional)",
  "contact_linkedin": "string (optional)",
  "contact_email": "string (optional)",
  "outreach_type": "string (optional)",
  "sender_persona": "string (optional)",
  "status": "not_started | sent | replied | meeting_booked | closed_won | closed_lost (optional)",
  "message_variant": "string (optional)",
  "sent_at": "datetime (optional)",
  "replied_at": "datetime (optional)",
  "notes": "string (optional)"
}
```

**Response:** `PipelineRecordResponse`

---

### Delete Pipeline Record

**`DELETE /api/v1/pif-pipeline/{record_id}`**

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `record_id` | UUID | Pipeline record ID |

**Response:**
```json
{
  "status": "success",
  "message": "Pipeline record deleted"
}
```

---

## Data Models

### PifInfoResponse

The complete firm record returned by `GET /api/v1/pif-info/{pif_id}` and included in list responses.

```json
{
  "id": "uuid",
  "firm_name": "string",
  "website": "string",
  "emails": ["string"],
  "phones": ["string"],
  "fax": "string",
  "addresses": ["string"],
  "contacts": [
    {
      "name": "string",
      "title": "string",
      "email": "string",
      "phone": "string",
      "extension": "string"
    }
  ],
  "conversation_ids": ["string"],
  "extraction_notes": "string",
  "leadership": [
    {
      "name": "string",
      "title": "string",
      "email": "string",
      "phone": "string",
      "linkedin": "string",
      "bio": "string",
      "education": ["string"],
      "skills": ["string"],
      "certifications": ["string"],
      "bar_admissions": ["string"],
      "cases_handled": ["string"],
      "experience": ["string"]
    }
  ],
  "research_data": {
    "practice_areas": ["string"],
    "founded_year": 0,
    "firm_size": "string",
    "office_locations": ["string"],
    "notable_cases": ["string"],
    "awards": ["string"],
    "bar_associations": ["string"],
    "social_media": {},
    "sources": ["string"]
  },
  "research_status": "pending | in_progress | completed | failed",
  "last_researched_at": "datetime",
  "staff": [
    {
      "name": "string",
      "title": "string",
      "role_category": "intake_specialist | case_manager | paralegal | office_manager | billing_coordinator | medical_records | other",
      "email": "string",
      "phone": "string",
      "linkedin": "string",
      "bio": "string"
    }
  ],
  "staff_research_status": "pending | in_progress | completed | failed",
  "behavioral_data": {
    "total_emails": 0,
    "monthly_volume": {"2025-01": 5},
    "last_contact_date": "datetime",
    "topic_distribution": {"scheduling": 0.4},
    "sender_roles": {"attorney": 5},
    "peak_contact_days": ["Monday"],
    "after_hours_ratio": 0.15
  },
  "icp_score": 85,
  "icp_tier": "A",
  "score_breakdown": {
    "volume_score": 25,
    "recency_score": 20,
    "topic_diversity_score": 15,
    "engagement_score": 25
  },
  "icp_scored_at": "datetime",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### PipelineRecordResponse

```json
{
  "id": "uuid",
  "pif_id": "uuid",
  "contact_name": "string",
  "contact_linkedin": "string",
  "contact_email": "string",
  "outreach_type": "linkedin_connection | linkedin_inmail | email | referral",
  "sender_persona": "pranav | neha",
  "status": "not_started | sent | replied | meeting_booked | closed_won | closed_lost",
  "message_variant": "string",
  "sent_at": "datetime",
  "replied_at": "datetime",
  "notes": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

---

## Deployment Details

| Property | Value |
|----------|-------|
| **Host** | `https://emailprocessing.mediflow360.com` |
| **Backend Port** | 8444 (HTTPS with SSL) |
| **Frontend Port** | 3001 (Next.js) |
| **Authentication** | None on PIF endpoints |
| **CORS** | `allow_origins=["*"]` |
| **Network** | `network_mode: host` (Docker) |

### Frontend

The Next.js frontend at `/settings/pifstats` consumes these APIs via `PifApi` and `PipelineApi` classes in `frontend/settings2/lib/api.ts`.

### Background Tasks

Research, behavior analysis, and scoring endpoints queue Celery tasks. Use the `task_id` returned by these endpoints to poll `/api/v1/pif-info/research-status/{task_id}` for completion.
