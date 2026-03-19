# REST API Reference

Base URL: `/api/v1/`

Interactive documentation (Swagger UI): `/api/docs/`

OpenAPI schema (JSON): `/api/schema/`

---

## Authentication

Currently no authentication is required for read-only endpoints. All endpoints are read-only (GET only) except the scan trigger.

---

## Pagination

List endpoints return paginated results:

```json
{
  "count": 142,
  "next": "http://localhost:8000/api/v1/bounties/?page=2",
  "previous": null,
  "results": [...]
}
```

Default page size: 25. Configurable in `settings.py` via `REST_FRAMEWORK["PAGE_SIZE"]`.

---

## Filtering, Search, and Ordering

All list endpoints support:

**Filtering** (exact match on specified fields):
```
GET /api/v1/bounties/?platform=github&status=evaluated
GET /api/v1/bounties/?language=Python
```

**Search** (full-text on title, description, repo_owner, repo_name):
```
GET /api/v1/bounties/?search=authentication
```

**Ordering** (prefix with `-` for descending):
```
GET /api/v1/bounties/?ordering=-bounty_amount_usd
GET /api/v1/bounties/?ordering=evaluation__roi_score
```

---

## Endpoints

### Bounties

#### `GET /api/v1/bounties/`

List all bounties. Returns summary fields.

**Filter fields:** `platform`, `status`, `language`

**Search fields:** `title`, `description`, `repo_owner`, `repo_name`

**Ordering fields:** `bounty_amount_usd`, `discovered_at`, `evaluation__roi_score`

**Response:**

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "platform": "github",
      "title": "Fix authentication bug in login flow",
      "repo_owner": "someorg",
      "repo_name": "someproject",
      "bounty_amount_usd": "200.00",
      "language": "Python",
      "status": "evaluated",
      "source_url": "https://github.com/someorg/someproject/issues/42",
      "competitors_count": 2,
      "discovered_at": "2026-03-19T10:00:00Z",
      "roi_score": 72.5,
      "estimated_hours": 3.0,
      "effective_hourly_rate": "66.67"
    }
  ]
}
```

---

#### `GET /api/v1/bounties/{id}/`

Retrieve a single bounty with full detail including nested evaluation.

**Response:**

```json
{
  "id": 1,
  "external_id": "12345",
  "platform": "github",
  "source_url": "https://github.com/someorg/someproject/issues/42",
  "title": "Fix authentication bug in login flow",
  "description": "The login flow fails when the user has special characters...",
  "repo_owner": "someorg",
  "repo_name": "someproject",
  "repo_url": "https://github.com/someorg/someproject",
  "issue_number": 42,
  "bounty_amount_usd": "200.00",
  "currency": "USD",
  "language": "Python",
  "labels": ["bug", "bounty"],
  "status": "evaluated",
  "competitors_count": 2,
  "existing_prs": 0,
  "discovered_at": "2026-03-19T10:00:00Z",
  "updated_at": "2026-03-19T10:05:00Z",
  "evaluation": {
    "id": 1,
    "bounty": 1,
    "roi_score": 72.5,
    "difficulty_score": 35.0,
    "tech_match_score": 95.0,
    "competition_score": 80.0,
    "repo_quality_score": 70.0,
    "estimated_hours": 3.0,
    "estimated_difficulty": "easy",
    "effective_hourly_rate": "66.67",
    "analysis_summary": "Clear bug fix needed in the auth validation logic.",
    "approach_suggestion": "Update the password validation regex to handle special chars.",
    "required_skills": ["Python", "Django"],
    "risks": [],
    "has_clear_requirements": true,
    "has_tests": true,
    "has_ci": true,
    "has_contribution_guide": false,
    "auto_rejected": false,
    "rejection_reason": "",
    "evaluated_at": "2026-03-19T10:05:00Z"
  }
}
```

---

#### `GET /api/v1/bounties/top_opportunities/`

Returns the top evaluated bounties ordered by ROI score. Excludes auto-rejected bounties.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | `10` | Maximum number of results |

**Example:**
```
GET /api/v1/bounties/top_opportunities/?limit=5
```

**Response:** Same format as list endpoint (array of summary objects).

---

#### `GET /api/v1/bounties/active/`

Returns bounties currently being worked on (status: `targeted`, `in_progress`, `submitted`).

**Response:** Same format as list endpoint.

---

### Evaluations

#### `GET /api/v1/evaluations/`

List all bounty evaluations.

**Filter fields:** `estimated_difficulty`, `auto_rejected`

**Ordering fields:** `roi_score`, `estimated_hours`, `effective_hourly_rate`

**Example — list rejected bounties:**
```
GET /api/v1/evaluations/?auto_rejected=true
```

**Example — list hard bounties by ROI:**
```
GET /api/v1/evaluations/?estimated_difficulty=hard&ordering=-roi_score
```

---

#### `GET /api/v1/evaluations/{id}/`

Full evaluation detail (all fields).

---

### Submissions

#### `GET /api/v1/submissions/`

List all PR submissions.

**Filter fields:** `pr_status`, `bounty_claimed`

**Ordering fields:** `submitted_at`

**PR status values:** `submitted`, `review_requested`, `changes_requested`, `approved`, `merged`, `closed`, `rejected`

**Example — list merged PRs:**
```
GET /api/v1/submissions/?pr_status=merged
```

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "bounty": 1,
      "bounty_title": "Fix authentication bug in login flow",
      "bounty_amount": "200.00",
      "pr_url": "https://github.com/someorg/someproject/pull/99",
      "pr_number": 99,
      "pr_title": "fix: handle special characters in password validation",
      "pr_status": "merged",
      "bounty_claimed": true,
      "submitted_at": "2026-03-19T12:00:00Z",
      "merged_at": "2026-03-20T09:30:00Z"
    }
  ]
}
```

---

#### `GET /api/v1/submissions/{id}/`

Full submission detail including `pr_body`, `review_comments`, `bounty_claim_url`.

---

### Earnings

#### `GET /api/v1/earnings/`

List all earning records.

**Filter fields:** `payment_status`

**Ordering fields:** `amount_usd`, `earned_at`

**Payment status values:** `pending`, `processing`, `paid`, `disputed`

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "bounty": 1,
      "bounty_title": "Fix authentication bug in login flow",
      "platform": "github",
      "amount_usd": "200.00",
      "platform_fee_usd": "0.00",
      "agent_cost_usd": "0.85",
      "net_earning_usd": "199.15",
      "payment_status": "paid",
      "total_time_hours": 2.5,
      "effective_hourly_rate": "79.66",
      "earned_at": "2026-03-20T09:30:00Z",
      "paid_at": "2026-03-21T14:00:00Z"
    }
  ]
}
```

---

#### `GET /api/v1/earnings/{id}/`

Full earning detail including `payment_method`, `payment_reference`.

---

### Dashboard

#### `GET /api/v1/dashboard/`

Aggregated statistics across the entire system. No pagination.

**Response:**

```json
{
  "bounties": {
    "total": 142,
    "by_status": {
      "discovered": 80,
      "evaluated": 40,
      "targeted": 5,
      "in_progress": 3,
      "submitted": 4,
      "merged": 8,
      "paid": 2
    }
  },
  "submissions": {
    "total_submitted": 12,
    "total_merged": 8,
    "total_rejected": 2,
    "total_pending": 2
  },
  "earnings": {
    "total_earned": "1240.50",
    "total_pending": "200.00",
    "total_paid": "1040.50",
    "avg_earning": "155.06",
    "avg_hourly_rate": "62.40"
  },
  "performance": {
    "win_rate": 66.7,
    "total_attempted": 12,
    "total_won": 8
  }
}
```

**Null values:** `earnings` fields will be `null` if no earnings exist yet.

---

### Scout Trigger

#### `GET /api/v1/scout/scan/`

Triggers an asynchronous full scan across all platforms via Celery.

**Response:**
```json
{"status": "scan_triggered"}
```

The scan runs in the background. Check `ScanLog` records or the Celery worker logs to monitor progress.

---

## Error Responses

Standard DRF error format:

```json
{
  "detail": "Not found."
}
```

**Status codes used:**
- `200 OK` — success
- `404 Not Found` — resource doesn't exist
- `400 Bad Request` — invalid query parameters

---

## API Documentation (Interactive)

Visit `/api/docs/` in your browser for the full interactive Swagger UI. You can browse all endpoints, see request/response schemas, and make test requests directly from the browser.

The raw OpenAPI JSON schema is available at `/api/schema/`.
