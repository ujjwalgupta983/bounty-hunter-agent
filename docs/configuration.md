# Configuration Reference

All configuration is managed through environment variables loaded from `config/.env`. Copy the template to get started:

```bash
cp config/.env.example config/.env
# Edit config/.env with your values
```

---

## Quick Setup

Minimum required variables to run the system locally:

```bash
GITHUB_TOKEN=ghp_your_personal_access_token
ANTHROPIC_API_KEY=sk-ant-your-api-key
```

Everything else has sensible defaults for local development.

---

## Full Variable Reference

### Core Django

| Variable | Type | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | string | `dev-secret-key-change-in-prod` | Django secret key. **Required in production — change this.** |
| `DEBUG` | bool | `False` | Enable Django debug mode. Never set `True` in production. |
| `ALLOWED_HOSTS` | list | `localhost,127.0.0.1` | Comma-separated list of allowed host headers. |
| `DATABASE_URL` | URL | `sqlite:///db.sqlite3` | Database connection URL. See formats below. |
| `REDIS_URL` | URL | `redis://localhost:6379/0` | Redis URL for Celery broker and cache. |

**`DATABASE_URL` formats:**

```bash
# SQLite (local dev)
DATABASE_URL=sqlite:///db.sqlite3

# PostgreSQL (production)
DATABASE_URL=postgres://user:password@host:5432/dbname

# PostgreSQL with SSL
DATABASE_URL=postgres://user:password@host:5432/dbname?sslmode=require
```

---

### GitHub Integration

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `GITHUB_TOKEN` | string | `""` | Yes | GitHub Personal Access Token (PAT). Needs `repo`, `read:user` scopes. |
| `GITHUB_USERNAME` | string | `""` | No | GitHub username for fork operations (used by Submitter). |

**Creating a GitHub PAT:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token"
3. Select scopes: `repo` (for private repos) or `public_repo` (for public only)
4. Copy the token — it's only shown once

---

### AI Provider

| Variable | Type | Default | Description |
|---|---|---|---|
| `ANALYST_AI_PROVIDER` | string | `anthropic` | AI provider for bounty analysis. Options: `anthropic`, `openai`, `openrouter` |
| `ANALYST_AI_MODEL` | string | `""` | Specific model to use. Leave blank to use provider default. |
| `ANTHROPIC_API_KEY` | string | `""` | Required when `ANALYST_AI_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | string | `""` | Required when `ANALYST_AI_PROVIDER=openai` |
| `OPENROUTER_API_KEY` | string | `""` | Required when `ANALYST_AI_PROVIDER=openrouter` |

**Provider defaults (when `ANALYST_AI_MODEL` is blank):**

| Provider | Default model |
|---|---|
| `anthropic` | `claude-sonnet-4-20250514` |
| `openai` | `gpt-4o-mini` |
| `openrouter` | `openrouter/auto` (OpenRouter picks best available) |

**OpenRouter** provides access to 100+ models (Claude, GPT-4o, Gemini, Llama, etc.) through a single OpenAI-compatible API. This is useful for cost optimization or trying different models.

```bash
# Use OpenRouter with a specific model
ANALYST_AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-your-key
ANALYST_AI_MODEL=anthropic/claude-3-haiku  # cheaper, faster
```

---

### Scout Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `SCOUT_MIN_BOUNTY_USD` | int | `50` | Minimum bounty amount (USD) to consider. Bounties below this are auto-rejected. |
| `SCOUT_MAX_BOUNTY_AGE_DAYS` | int | `90` | Maximum age of a bounty issue in days. Older issues are auto-rejected. |
| `SCOUT_SCAN_INTERVAL_HOURS` | int | `6` | How often (in hours) to run a full scan across all platforms. |

**Example — aggressive filtering for high-value bounties only:**

```bash
SCOUT_MIN_BOUNTY_USD=200
SCOUT_MAX_BOUNTY_AGE_DAYS=30
SCOUT_SCAN_INTERVAL_HOURS=2
```

---

### Analyst Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `ANALYST_MIN_ROI_SCORE` | float | `40.0` | Minimum ROI score (0–100) for a bounty to be picked by the Picker. |

**ROI score interpretation:**
- `0–30` — Low value / high competition / poor tech match
- `30–60` — Moderate opportunity
- `60–80` — Good opportunity
- `80–100` — Excellent opportunity

Lower `ANALYST_MIN_ROI_SCORE` means more bounties get picked (higher quantity, lower average quality). Higher means fewer but better-quality targets.

---

### Solver Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `SOLVER_MAX_CONCURRENT` | int | `5` | Maximum number of bounties being solved simultaneously. |
| `SOLVER_TIMEOUT_MULTIPLIER` | float | `2.0` | Abandon solver after `estimated_hours × SOLVER_TIMEOUT_MULTIPLIER` hours. |
| `SOLVER_MAX_ITERATIONS` | int | `3` | Maximum solve-review-iterate cycles before giving up. |
| `SOLVER_CODING_AGENT` | string | `claude` | AI coding agent backend. Options: `claude` (Claude Code), others planned. |

**Concurrency vs. resource use:**
- Each concurrent solver uses AI inference tokens and disk space (cloned repos)
- For a single-machine setup, `SOLVER_MAX_CONCURRENT=2` or `3` is recommended
- In a Kubernetes/Docker Swarm setup, this can be higher

---

### Submitter Settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `SUBMITTER_HUMAN_REVIEW_FIRST_N` | int | `20` | Require human approval for the first N PR submissions. Set to `0` to disable. |
| `SUBMITTER_RATE_LIMIT_PER_HOUR` | int | `3` | Maximum PRs to submit per hour across all platforms. |

**Why human review for first N?** The system's first submissions establish your reputation on platforms. Human review catches any issues with the PR format, code quality, or scope before the system runs fully autonomously.

---

### Telegram Notifications

| Variable | Type | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | string | `""` | Telegram bot token from @BotFather. Leave blank to disable notifications. |
| `TELEGRAM_CHAT_ID` | string | `""` | Chat or channel ID to send notifications to. |

**Setting up Telegram notifications:**
1. Message @BotFather on Telegram: `/newbot` — follow prompts
2. Copy the bot token: `123456789:ABCdef...`
3. Start a chat with your bot or add it to a channel
4. Get the chat ID: send a message, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Set `TELEGRAM_CHAT_ID` to the `chat.id` value from the response

---

## Environment File Example

```bash
# config/.env

# ── Django ────────────────────────────────────────────────────────────
SECRET_KEY=your-very-long-random-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
DATABASE_URL=postgres://bounty:password@localhost:5432/bounty_hunter
REDIS_URL=redis://localhost:6379/0

# ── GitHub ────────────────────────────────────────────────────────────
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_USERNAME=your-github-username

# ── AI Provider ───────────────────────────────────────────────────────
ANALYST_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
# ANALYST_AI_MODEL=                  # blank = use provider default

# ── Scout ─────────────────────────────────────────────────────────────
SCOUT_MIN_BOUNTY_USD=50
SCOUT_MAX_BOUNTY_AGE_DAYS=90
SCOUT_SCAN_INTERVAL_HOURS=6

# ── Analyst ───────────────────────────────────────────────────────────
ANALYST_MIN_ROI_SCORE=40.0

# ── Solver ────────────────────────────────────────────────────────────
SOLVER_MAX_CONCURRENT=5
SOLVER_TIMEOUT_MULTIPLIER=2.0
SOLVER_MAX_ITERATIONS=3
SOLVER_CODING_AGENT=claude

# ── Submitter ─────────────────────────────────────────────────────────
SUBMITTER_HUMAN_REVIEW_FIRST_N=20
SUBMITTER_RATE_LIMIT_PER_HOUR=3

# ── Notifications ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Configuration in Code

Settings are accessible in Python via `django.conf.settings.BOUNTY_HUNTER`:

```python
from django.conf import settings

min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]      # int
ai_provider = settings.BOUNTY_HUNTER["AI_PROVIDER"]         # str
max_solvers = settings.BOUNTY_HUNTER["MAX_CONCURRENT_SOLVERS"]  # int
```

The full `BOUNTY_HUNTER` dict is defined in `bounty_hunter/settings.py`.

---

## Production Checklist

Before going to production:

- [ ] Set `SECRET_KEY` to a random 50+ character string
- [ ] Set `DEBUG=False`
- [ ] Set `ALLOWED_HOSTS` to your actual domain(s)
- [ ] Use `DATABASE_URL` pointing to PostgreSQL (not SQLite)
- [ ] Set `REDIS_URL` to your Redis instance
- [ ] Set `GITHUB_TOKEN` with appropriate scopes
- [ ] Set at least one AI provider key
- [ ] Set `SUBMITTER_HUMAN_REVIEW_FIRST_N=20` (keep until you trust the system)
- [ ] Optionally configure Telegram notifications
- [ ] Run `python manage.py check --deploy` to catch Django deployment issues
