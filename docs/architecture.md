# Architecture — Bounty Hunter Agent

## Overview

Bounty Hunter Agent is an autonomous system that discovers software bounties on the internet, evaluates them for ROI, solves them using AI coding agents, and submits pull requests to claim rewards — with minimal human intervention.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Bounty Hunter Agent                          │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────────┐  │
│  │  Scout   │───▶│ Analyst  │───▶│  Picker  │───▶│   Solver    │  │
│  │ (scrape) │    │ (score)  │    │ (select) │    │  (fix code) │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────┬──────┘  │
│       ▲                                                  │         │
│       │                                          ┌───────▼──────┐  │
│  External Platforms:                             │  Submitter   │  │
│  - GitHub Issues                                 │  (create PR) │  │
│  - Algora.io                                     └───────┬──────┘  │
│  - Opire (planned)                                       │         │
│  - Gitcoin (planned)                             ┌───────▼──────┐  │
│                                                  │   Tracker    │  │
│                                                  │ (monitor PR) │  │
│                                                  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │                                               │
         ▼                                               ▼
  ┌─────────────┐                                ┌─────────────┐
  │  PostgreSQL  │                                │   Redis     │
  │  (database)  │                                │  (broker)   │
  └─────────────┘                                └─────────────┘
```

## Agent Modules

### Scout

**Location:** `bounty_hunter/scouts/`

The Scout layer scrapes bounty platforms on a periodic Celery Beat schedule. Each platform has its own scout class implementing a `scan() -> dict` method.

**Current implementations:**
- `github_scout.py` — Searches GitHub Issues API for bounty-labeled issues. Extracts dollar amounts from titles, labels, and issue bodies using regex. Handles pagination and rate limits.
- `algora_scout.py` — Queries the Algora.io GraphQL API with an httpx web scraping fallback.

**Output:** Creates or updates `Bounty` model records with status `discovered`. Logs scan runs in `ScanLog`.

**Celery task:** `bounty_hunter.scouts.tasks.run_full_scan` — runs all scouts sequentially and triggers evaluation of any new bounties discovered.

---

### Analyst

**Location:** `bounty_hunter/analyst/`

The Analyst evaluates each discovered bounty using a multi-factor ROI scoring formula and an AI provider for difficulty estimation.

**ROI Scoring Formula:**
```
ROI = (bounty_amount / estimated_hours) × tech_match × competition_factor × repo_quality × inverse_difficulty
```
All sub-scores are normalized to 0–100. Final score is normalized to 0–100.

**Sub-scores:**
| Factor | Description | Source |
|---|---|---|
| `tech_match_score` | How well the repo's language/stack matches our strengths | Language detection + label scanning |
| `competition_score` | Inverse of existing PRs + competitors | `existing_prs` + `competitors_count` |
| `difficulty_score` | AI-estimated difficulty 0–100 | `_analyze_with_ai()` → AI provider |
| `repo_quality_score` | Does the repo have tests, CI, contributing guide | GitHub API |
| `estimated_hours` | AI-estimated time to fix | `_analyze_with_ai()` |

**Auto-rejection rules** (no AI call made):
- Bounty amount < `SCOUT_MIN_BOUNTY_USD` (default: $50)
- More than 5 existing PRs
- More than 10 competitors
- Description shorter than 50 chars AND no title
- Issue older than `SCOUT_MAX_BOUNTY_AGE_DAYS` days (default: 90)

**AI Provider:** Configurable via `ANALYST_AI_PROVIDER`. Supports `anthropic`, `openai`, and `openrouter`. Falls back to hardcoded defaults if the AI call fails.

**Output:** Creates `Evaluation` records linked to each `Bounty`. Updates bounty status to `evaluated`.

---

### Picker

**Location:** `bounty_hunter/picker/`

The Picker selects which evaluated bounties to actually work on, respecting concurrency limits.

**Logic:**
1. Count bounties currently `targeted` or `in_progress`
2. If `active_count >= MAX_CONCURRENT_SOLVERS`, return `{"reason": "at capacity"}`
3. Query `evaluated` bounties with `roi_score >= MIN_ROI_SCORE`, ordered by score descending
4. Claim up to `available_slots` bounties by setting status to `targeted`

**Celery task:** `bounty_hunter.picker.tasks.pick_targets` — called after each full scan.

---

### Solver (WIP)

**Location:** `bounty_hunter/solver/`

The Solver is an AI coding agent swarm that clones the target repository, understands the codebase, implements a fix, and runs the test suite. It self-reviews and iterates up to `SOLVER_MAX_ITERATIONS` times.

**Planned phases:**
1. `exploring` — understand repo structure and codebase
2. `planning` — produce implementation plan
3. `coding` — implement the fix
4. `testing` — run existing test suite
5. `reviewing` — internal quality check
6. `iterating` — revise if tests fail or review finds issues
7. `ready` — signal Submitter to create PR

---

### Submitter (WIP)

**Location:** `bounty_hunter/submitter/`

The Submitter creates a professional pull request in the target repository using PyGithub or the `gh` CLI. It reads `CONTRIBUTING.md` of the target repo before writing the PR description.

**Safety gate:** The first `SUBMITTER_HUMAN_REVIEW_FIRST_N` submissions (default: 20) require human approval before the PR is created.

---

### Tracker (WIP)

**Location:** `bounty_hunter/tracker/`

The Tracker polls open PRs for status changes, responds to code review comments using the AI, and records payments in the `Earning` model once a PR is merged and paid.

**Celery task:** `bounty_hunter.tracker.tasks.check_all_prs` — runs every hour.

---

## Data Flow

```
1. SCOUT runs on schedule
   └─▶ Creates Bounty (status=discovered)
         └─▶ Triggers evaluate_new_bounties.delay()

2. ANALYST evaluates each discovered bounty
   ├─▶ Auto-rejected? → Evaluation(auto_rejected=True), Bounty(status=evaluated)
   └─▶ Scored?        → Evaluation(roi_score=N), Bounty(status=evaluated)
         └─▶ Triggers pick_targets.delay()

3. PICKER selects top bounties
   └─▶ Bounty(status=targeted)
         └─▶ Triggers solve_bounty.delay(bounty.id)  [planned]

4. SOLVER works the fix
   └─▶ Solution(status=ready, all_tests_pass=True)
         └─▶ Triggers submit_solution.delay(solution.id)  [planned]

5. SUBMITTER creates PR
   └─▶ Submission(pr_url=..., pr_status=submitted)
   └─▶ Bounty(status=submitted)

6. TRACKER monitors PR
   ├─▶ PR merged   → Bounty(status=merged), Earning created
   ├─▶ PR rejected → Bounty(status=rejected)
   └─▶ Review comments → AI generates response, pushes updated code
```

---

## Django Model Relationships

```
Bounty (1)
  │
  ├──── Evaluation (1:1)     — ROI score, AI analysis, difficulty
  │
  ├──── Solution (1:many)    — Code changes, test results
  │        │
  │        └──── Submission (1:1)   — PR URL, PR status, review comments
  │                 │
  │                 └──── Earning (1:1)   — Payment tracking, net profit
  │
  └──── ScanLog (independent) — Scout run history per platform
```

**Status transitions:**

```
discovered ──▶ evaluated ──▶ targeted ──▶ in_progress ──▶ solved ──▶ submitted ──▶ merged ──▶ paid
                   │               │                                      │
                   ▼               ▼                                      ▼
               rejected        abandoned                              rejected
                                   ▼
                               expired
```

---

## Celery Task Schedule

| Task | Schedule | Description |
|---|---|---|
| `scouts.tasks.run_full_scan` | Every N hours (default: 6) | Scrape all platforms, trigger evaluation |
| `tracker.tasks.check_all_prs` | Every hour | Poll open PR statuses, respond to reviews |
| `analyst.tasks.rescore_stale_bounties` | Daily | Re-evaluate bounties whose scores may be stale |

The schedule interval is configurable via `SCOUT_SCAN_INTERVAL_HOURS`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django 5.x + Django REST Framework |
| Task queue | Celery 5.x |
| Message broker | Redis |
| Result backend | Django DB (via django-celery-results) |
| Scheduler | Celery Beat (via django-celery-beat) |
| Database | PostgreSQL (prod) / SQLite (dev) |
| AI providers | Anthropic Claude (primary), OpenAI, OpenRouter |
| HTTP client | httpx (async-capable, used for scraping) |
| Git operations | PyGithub + `gh` CLI |
| API docs | drf-spectacular (OpenAPI/Swagger) |

---

## Directory Structure

```
bounty-hunter-agent/
├── bounty_hunter/              # Django project root
│   ├── settings.py             # All configuration (reads from config/.env)
│   ├── celery.py               # Celery app + autodiscover
│   ├── urls.py                 # URL routing
│   ├── views.py                # Dashboard HTML view
│   ├── models/
│   │   └── models.py           # All data models
│   ├── scouts/                 # Platform scrapers
│   │   ├── github_scout.py
│   │   ├── algora_scout.py
│   │   └── tasks.py            # run_full_scan, scan_github, scan_algora
│   ├── analyst/
│   │   ├── scorer.py           # BountyAnalyst: ROI scoring + AI difficulty
│   │   └── tasks.py            # evaluate_new_bounties, rescore_stale_bounties
│   ├── picker/
│   │   └── tasks.py            # pick_targets
│   ├── solver/                 # (WIP)
│   ├── submitter/              # (WIP)
│   ├── tracker/                # (WIP)
│   ├── api/
│   │   ├── urls.py
│   │   ├── views.py            # ViewSets + DashboardView
│   │   └── serializers.py
│   └── utils/
│       ├── ai_client.py        # Multi-provider AI client
│       └── guardrails.py       # Safety checks
├── config/
│   └── .env.example
├── docs/                       # This directory
├── tests/
│   ├── conftest.py             # Shared pytest fixtures
│   ├── test_models.py
│   ├── test_analyst.py
│   ├── test_api.py
│   ├── test_picker.py
│   └── test_ai_client.py
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
└── manage.py
```
