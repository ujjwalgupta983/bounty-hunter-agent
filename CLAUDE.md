# CLAUDE.md — Bounty Hunter Agent

## What This Project Is

An autonomous AI-powered bounty hunting system that scrapes bounty issues from across the internet, evaluates them for ROI, solves them using coding agents, and submits PRs to claim the bounty. Built with Django, Celery, and multiple AI providers.

## Architecture

```
Scout (scrape) → Analyst (score) → Picker (select) → Solver (fix) → Submitter (PR) → Tracker (monitor)
```

- **Scout agents** scrape bounty platforms (GitHub, Algora, Opire, etc.) on a schedule
- **Analyst** uses AI + heuristics to score bounties by ROI (payout / estimated hours × tech match × competition)
- **Picker** selects top N targets based on ROI and current capacity (max 5 concurrent)
- **Solver swarm** clones repo, understands codebase, implements fix, runs tests, self-reviews
- **Submitter** creates professional PRs following each repo's contribution guidelines
- **Tracker** monitors PR status, responds to review feedback, tracks payments

## Tech Stack

- **Backend:** Django 5.x + Django REST Framework
- **Task Queue:** Celery 5.x + Redis (broker + cache)
- **Database:** PostgreSQL (prod) / SQLite (dev)
- **AI:** Anthropic Claude (primary), OpenAI (fallback)
- **Git:** PyGithub + `gh` CLI
- **Scraping:** httpx + BeautifulSoup4
- **Container:** Docker + Docker Compose
- **Docs/API:** drf-spectacular (OpenAPI/Swagger)

## Project Structure

```
bounty-hunter-agent/
├── bounty_hunter/           # Django project root
│   ├── settings.py          # Django settings (reads from config/.env)
│   ├── celery.py            # Celery app configuration
│   ├── urls.py              # URL routing
│   ├── models/              # Django models (Bounty, Evaluation, Solution, Submission, Earning)
│   │   └── models.py        # All data models
│   ├── scouts/              # Platform scrapers
│   │   ├── github_scout.py  # GitHub Issues bounty scraper
│   │   ├── algora_scout.py  # Algora.io bounty scraper
│   │   └── tasks.py         # Celery tasks for scanning
│   ├── analyst/             # Bounty evaluation & scoring
│   │   ├── scorer.py        # ROI scoring algorithm + AI difficulty estimation
│   │   └── tasks.py         # Celery tasks for evaluation
│   ├── picker/              # Target selection
│   │   └── tasks.py         # Picks top bounties by ROI within capacity
│   ├── solver/              # Coding agent swarm (WIP)
│   ├── submitter/           # PR creation & bounty claiming (WIP)
│   ├── tracker/             # PR monitoring & review response (WIP)
│   ├── api/                 # REST API
│   │   ├── urls.py          # API routes
│   │   ├── views.py         # ViewSets + Dashboard endpoint
│   │   └── serializers.py   # DRF serializers
│   └── utils/               # Shared utilities
├── config/
│   └── .env.example         # Environment variable template
├── docker/                  # Docker configs (WIP)
├── docs/                    # Documentation (WIP)
├── tests/                   # Test suite (WIP)
├── data/                    # Runtime data (gitignored)
├── Dockerfile               # Production container
├── requirements.txt         # Python dependencies
└── manage.py                # Django management script
```

## Key Models & Data Flow

```
Bounty (discovered from platform)
  └── Evaluation (AI-scored: ROI, difficulty, tech match)
        └── [status: TARGETED]
              └── Solution (code changes by solver agent)
                    └── Submission (PR created, bounty claimed)
                          └── Earning (payment tracked)
```

### Bounty Statuses
`discovered → evaluated → targeted → in_progress → solved → submitted → merged → paid`
Branch statuses: `rejected`, `abandoned`, `expired`

## Development Commands

```bash
# Setup
cp config/.env.example config/.env   # Then edit with your keys
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser

# Run
python manage.py runserver                          # Django
celery -A bounty_hunter worker -l info              # Celery worker
celery -A bounty_hunter beat -l info                # Celery scheduler

# Scout commands
python manage.py scout_scan                         # Full scan all platforms
python manage.py scout_scan --platform github       # Single platform

# API
# Dashboard:   GET /api/v1/dashboard/
# Bounties:    GET /api/v1/bounties/
# Top opps:    GET /api/v1/bounties/top_opportunities/
# Active:      GET /api/v1/bounties/active/
# Swagger:     GET /api/docs/
```

## Configuration

All config lives in `config/.env`. Key variables:

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | Yes | GitHub PAT with repo scope |
| `ANTHROPIC_API_KEY` | Yes* | For AI analysis (*or OPENAI_API_KEY) |
| `DATABASE_URL` | No | Defaults to SQLite |
| `REDIS_URL` | No | Defaults to localhost:6379 |
| `SCOUT_MIN_BOUNTY_USD` | No | Minimum bounty to consider (default: $50) |
| `SOLVER_MAX_CONCURRENT` | No | Max parallel bounties (default: 5) |
| `SUBMITTER_HUMAN_REVIEW_FIRST_N` | No | Require human approval for first N PRs (default: 20) |

## Coding Conventions

- **Python 3.11+** — use modern syntax (type hints, match statements, f-strings)
- **Django style** — fat models, thin views. Business logic in model methods or dedicated service modules, not in views.
- **Celery tasks** — keep tasks thin. Import heavy dependencies inside the task function to avoid circular imports.
- **Imports** — use absolute imports from `bounty_hunter.` prefix
- **Logging** — use `structlog` or stdlib `logging`. Always include context (bounty ID, platform, amounts).
- **Error handling** — catch specific exceptions. Log errors with context. Never silently swallow exceptions.
- **Tests** — use pytest + factory-boy. Mock external APIs (GitHub, Algora, AI providers). Never hit real APIs in tests.
- **Commits** — conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Important Patterns

### Adding a New Scout
1. Create `bounty_hunter/scouts/newplatform_scout.py`
2. Implement class with `scan() -> dict` method
3. Normalize data to `Bounty` model fields
4. Handle pagination, rate limits, and errors gracefully
5. Register in `bounty_hunter/scouts/tasks.py` inside `run_full_scan()`
6. Add tests with mocked API responses

### ROI Scoring Formula
```
ROI = (bounty_amount / estimated_hours) × tech_match × competition_factor × repo_quality × inverse_difficulty
```
All factors normalized to 0-1 range. Final score normalized to 0-100.

### Auto-Rejection Rules (Analyst)
- Bounty < $50 (configurable)
- More than 5 existing PRs
- More than 10 competitors
- Description < 50 chars with no title
- Issue older than 90 days (configurable)

## Guardrails (Critical — Do Not Bypass)

1. **Never submit a PR without ALL existing tests passing**
2. **Never modify files outside the scope of the issue**
3. **Always read and follow CONTRIBUTING.md of target repos**
4. **Human review required for first 20 submissions** (configurable via `SUBMITTER_HUMAN_REVIEW_FIRST_N`)
5. **Rate limit submissions** — max N per hour per platform
6. **Time-box solver** — abandon after 2× estimated hours
7. **Never commit secrets, tokens, or credentials**
8. **Flag architectural/complex changes for human review instead of auto-submitting**

## Current Status (WIP)

### ✅ Built
- Django project structure + settings
- All data models (Bounty, Evaluation, Solution, Submission, Earning, ScanLog)
- GitHub Scout (searches bounty-labeled issues)
- Algora Scout (API + web scraping fallback)
- Analyst/Scorer (AI difficulty estimation + ROI calculation)
- Picker (target selection by ROI + capacity)
- REST API (CRUD + dashboard + top opportunities)
- Celery configuration with Beat schedule
- Dockerfile

### 🚧 In Progress
- Solver swarm pipeline (Issue #2)
- Submitter agent (Issue #3)
- Docker Compose (Issue #5)

### 📋 Planned
- Tracker agent (Issue #4)
- More scouts: Opire, Gitcoin, Immunefi (Issue #1)
- Dashboard UI (Issue #6)
- Telegram notifications (Issue #7)
- Test suite (Issue #8)
- Full documentation (Issue #9)
- n8n workflows (Issue #10)
- Safety guardrails implementation (Issue #11)
- Management commands (Issue #12)

## Debugging Tips

- **Scout not finding bounties?** Check `GITHUB_TOKEN` has correct scopes. Check rate limits in response headers.
- **Analyst scoring weird?** Check AI provider API key. Scorer falls back to defaults if AI call fails.
- **Celery tasks not running?** Ensure Redis is running. Check `celery -A bounty_hunter worker -l debug` for errors.
- **Database issues?** Run `python manage.py migrate`. Check `DATABASE_URL` in .env.
- **Import errors?** Use absolute imports: `from bounty_hunter.models.models import Bounty`
