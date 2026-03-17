# 🎯 Bounty Hunter Agent

**AI-powered autonomous bounty hunter** — scrapes, evaluates, solves, and submits bounty issues across the internet.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Django](https://img.shields.io/badge/Django-5.x-green)
![Celery](https://img.shields.io/badge/Celery-5.x-orange)
![Docker](https://img.shields.io/badge/Docker-ready-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🏗️ Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   SCOUT      │───▶│   ANALYST    │───▶│   PICKER     │───▶│   SOLVER     │───▶│   SUBMITTER  │───▶│   TRACKER    │
│   Agent      │    │   Agent      │    │   Agent      │    │   Swarm      │    │   Agent      │    │   Agent      │
│              │    │              │    │              │    │              │    │              │    │              │
│ Scrapes all  │    │ Evaluates    │    │ Ranks by     │    │ Clones repo  │    │ Opens PR     │    │ Monitors PRs │
│ bounty       │    │ difficulty,  │    │ ROI and      │    │ Fixes issue  │    │ Claims       │    │ Responds to  │
│ platforms    │    │ payout,      │    │ picks top    │    │ Runs tests   │    │ bounty       │    │ reviews      │
│              │    │ tech stack   │    │ targets      │    │              │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

## ✨ Features

- **Multi-Platform Scraping** — GitHub Issues, Algora, Opire, Gitcoin, IssueHunt, and more
- **AI-Powered Evaluation** — Difficulty estimation, ROI scoring, tech stack matching
- **Autonomous Solving** — Coding agents clone, fix, test, and prepare PRs
- **Smart Submission** — Professional PR creation following repo contribution guidelines
- **Review Response** — Auto-responds to PR review comments
- **Earnings Dashboard** — Track bounties attempted, won, pending, and paid

## 📦 Tech Stack

| Component | Technology |
|---|---|
| **Backend / API** | Django 5.x + Django REST Framework |
| **Task Queue** | Celery + Redis |
| **Database** | PostgreSQL |
| **Coding Agents** | Claude Code / Codex (via subprocess) |
| **Workflow Engine** | n8n (optional, for complex orchestration) |
| **Scraping** | httpx + BeautifulSoup4 |
| **Git Operations** | GitPython + `gh` CLI |
| **Containerization** | Docker + Docker Compose |
| **Scheduling** | Celery Beat (periodic tasks) |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- GitHub CLI (`gh`) authenticated
- Redis (or use Docker)
- PostgreSQL (or use Docker)

### 1. Clone & Setup

```bash
git clone https://github.com/ujjwalgupta983/bounty-hunter-agent.git
cd bounty-hunter-agent
cp config/.env.example config/.env
# Edit config/.env with your API keys
```

### 2. Run with Docker (Recommended)

```bash
docker compose up -d
```

This starts:
- Django web server (port 8000)
- Celery worker (task execution)
- Celery Beat (scheduler)
- PostgreSQL database
- Redis (message broker)
- n8n (workflow engine, port 5678)

### 3. Run Locally (Development)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Django
python manage.py runserver

# Start Celery worker (separate terminal)
celery -A bounty_hunter worker -l info

# Start Celery Beat (separate terminal)
celery -A bounty_hunter beat -l info
```

### 4. Run a Scout Scan

```bash
# Via management command
python manage.py scout_scan

# Via API
curl -X POST http://localhost:8000/api/v1/scout/scan/

# Via Celery task
python manage.py shell -c "from bounty_hunter.scouts.tasks import run_full_scan; run_full_scan.delay()"
```

## 📊 Dashboard

Access the admin dashboard at `http://localhost:8000/admin/`

API documentation at `http://localhost:8000/api/docs/`

## 🔧 Configuration

See [docs/configuration.md](docs/configuration.md) for full configuration reference.

Key environment variables:

```bash
# Required
GITHUB_TOKEN=github_pat_xxx        # GitHub personal access token
OPENAI_API_KEY=sk-xxx              # For coding agents (or ANTHROPIC_API_KEY)

# Optional
ALGORA_API_KEY=xxx                 # Algora platform access
GITCOIN_API_KEY=xxx                # Gitcoin bounties
N8N_WEBHOOK_URL=http://n8n:5678    # n8n workflow triggers

# Database
DATABASE_URL=postgres://user:pass@localhost:5432/bounty_hunter

# Redis
REDIS_URL=redis://localhost:6379/0
```

## 📖 Documentation

- [Architecture Overview](docs/architecture.md)
- [Configuration Guide](docs/configuration.md)
- [Scout Plugins](docs/scouts.md)
- [Scoring Algorithm](docs/scoring.md)
- [Solver Pipeline](docs/solver.md)
- [Deployment Guide](docs/deployment.md)
- [n8n Workflows](docs/n8n-workflows.md)
- [API Reference](docs/api.md)

## 📈 Earnings Tracker

The system tracks all bounty activity:

```
$ python manage.py bounty_report

📊 Bounty Hunter Report (Last 30 Days)
─────────────────────────────────────
Bounties Scraped:     342
Bounties Evaluated:   342
Bounties Attempted:    38
PRs Submitted:         35
PRs Merged:            12
PRs Pending Review:     8
PRs Rejected:           5
Win Rate:            34.3%
─────────────────────────────────────
Earnings (Confirmed):  $2,840
Earnings (Pending):    $1,650
Total Pipeline:        $4,490
Avg $/Bounty Won:       $237
Avg Hours/Bounty:       3.2h
Effective Rate:      $74/hr
```

## ⚠️ Guardrails

- **Human-in-the-loop** for first 20 submissions (configurable)
- **Max 5 concurrent bounties** (prevents resource exhaustion)
- **Time-box per bounty** — auto-abandon after 2x estimated time
- **Test-first** — never submits without passing ALL existing tests
- **Style compliance** — follows each repo's contribution guidelines
- **Rate limiting** — natural pacing to avoid platform bans
- **Reputation tracking** — stops submitting to repos with high rejection rates

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

MIT — See [LICENSE](LICENSE) for details.

---

Built with 🐾 by the Bounty Hunter Team
