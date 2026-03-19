# Contributing to Bounty Hunter Agent

Thank you for your interest in contributing! This document covers everything you need to get started.

---

## Development Setup

### Prerequisites

- Python 3.11+
- Redis (for Celery)
- Git

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/ujjwalgupta983/bounty-hunter-agent.git
cd bounty-hunter-agent

# 2. Create and activate a virtual environment
python3.11 -m venv venv
source venv/bin/activate       # Linux/macOS
# venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp config/.env.example config/.env
# Edit config/.env with your GITHUB_TOKEN, ANTHROPIC_API_KEY, etc.

# 5. Run database migrations
python manage.py migrate

# 6. Create a superuser (optional, for Django admin)
python manage.py createsuperuser

# 7. Start Redis (required for Celery)
redis-server &

# 8. Verify the setup
python manage.py check
```

### Running the Application

```bash
# Django development server
python manage.py runserver

# Celery worker (in a separate terminal)
source venv/bin/activate
celery -A bounty_hunter worker -l info

# Celery Beat scheduler (in a separate terminal)
source venv/bin/activate
celery -A bounty_hunter beat -l info
```

---

## Running Tests

### Run all tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### Run specific test files

```bash
python -m pytest tests/test_models.py -v
python -m pytest tests/test_analyst.py -v
python -m pytest tests/test_api.py -v
```

### Run with coverage

```bash
python -m pytest tests/ --cov=bounty_hunter --cov-report=term-missing
```

### Test configuration

Tests use `pytest.ini` at the project root. The Django settings module is automatically set to `bounty_hunter.settings`.

Key fixtures are defined in `tests/conftest.py`:
- `bounty` — a sample `Bounty` in `discovered` status
- `evaluated_bounty` — a `Bounty` with an attached `Evaluation` (ROI score: 75)

**Important:** Never hit real external APIs in tests. Mock all HTTP calls and AI client calls.

```python
# Good: mock the AI call
with patch.object(analyst, "_analyze_with_ai", return_value=mock_response):
    result = analyst.evaluate(bounty)

# Good: mock httpx
with patch("bounty_hunter.scouts.github_scout.httpx.get") as mock_get:
    mock_get.return_value.json.return_value = {...}
    result = scout.scan()
```

---

## Code Style

### Python version

This project targets **Python 3.11+**. Use modern syntax:
- Type hints: `def scan(self) -> dict:`
- f-strings: `f"Found {count} bounties"`
- Match statements for multi-way branching
- `|` union types: `str | None`

### Django conventions

**Fat models, thin views.** Business logic belongs in:
- Model methods (for logic tightly coupled to a model)
- Dedicated service modules like `analyst/scorer.py`
- Celery tasks for anything async

Views should only handle HTTP concerns (request parsing, response formatting).

### Imports

Use absolute imports from the `bounty_hunter.` prefix:

```python
# Good
from bounty_hunter.models.models import Bounty, BountyStatus
from bounty_hunter.utils.ai_client import analyze_bounty

# Bad
from .models import Bounty
from models import Bounty
```

Inside Celery tasks, import heavy dependencies inside the task function to avoid slow worker startup:

```python
@shared_task
def run_full_scan():
    from bounty_hunter.scouts.github_scout import GitHubScout  # import here, not at top
    return GitHubScout().scan()
```

### Logging

Use the stdlib `logging` module. Always include context (bounty ID, platform, amounts):

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Evaluated bounty %d: ROI=%.1f", bounty.id, roi_score)
logger.warning("Scout failed for platform %s: %s", platform, exc)
logger.error("Submission failed for bounty %d: %s", bounty.id, exc, exc_info=True)
```

### Error handling

- Catch specific exceptions, not bare `except`
- Log errors with context before re-raising or returning fallbacks
- Never silently swallow exceptions

```python
# Good
try:
    result = scout.scan()
except httpx.HTTPStatusError as e:
    logger.error("GitHub API returned %d: %s", e.response.status_code, e)
    return {"error": str(e)}

# Bad
try:
    result = scout.scan()
except:
    pass
```

---

## How to Add a New Scout

See [docs/scouts.md](docs/scouts.md) for a complete step-by-step guide to adding a new bounty platform scout.

**Quick summary:**
1. Create `bounty_hunter/scouts/newplatform_scout.py` with a `NewPlatformScout` class
2. Implement `scan() -> dict` and `_normalize(item) -> dict | None`
3. Add `NEWPLATFORM = "newplatform"` to the `Platform` enum in `models.py`
4. Run `python manage.py makemigrations && python manage.py migrate`
5. Register the scout in `bounty_hunter/scouts/tasks.py`
6. Add any API keys to `settings.py` and `config/.env.example`
7. Write tests in `tests/test_newplatform_scout.py` (mock all HTTP)

---

## Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must start with a type prefix:

| Prefix | When to use |
|---|---|
| `feat:` | New feature or capability |
| `fix:` | Bug fix |
| `docs:` | Documentation changes only |
| `refactor:` | Code restructuring (no behavior change) |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance (deps, CI, tooling) |
| `perf:` | Performance improvement |

**Format:**
```
<type>: <short description (imperative, lowercase, no period)>

<optional body — explain WHY, not WHAT>

<optional footer — closes issues, co-authors>
```

**Examples:**

```
feat: add Opire scout for bounty discovery

Opire hosts JavaScript/TypeScript bounties with clear USD amounts.
Uses Opire's REST API with httpx. Falls back to web scraping if API
returns 403.

Closes #1
```

```
fix: handle special characters in bounty amount parsing

The regex failed on amounts like "$1,500.00" — added comma handling
to the AMOUNT_PATTERNS list.
```

```
test: add picker capacity limit test
```

---

## Pull Request Process

1. **Branch naming:** `feat/issue-N-short-description` or `fix/issue-N-short-description`

   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/issue-15-opire-scout
   ```

2. **Keep PRs focused.** One feature or fix per PR. Large changes are harder to review and more likely to introduce bugs.

3. **Write tests.** All new code should have tests. Aim for test coverage of the happy path and the main error cases.

4. **Run tests before pushing:**
   ```bash
   python manage.py check
   python -m pytest tests/ -v
   ```

5. **Update documentation.** If you add a scout, update `docs/scouts.md`. If you add a config variable, update `docs/configuration.md`.

6. **PR description should include:**
   - What the PR does (1-3 bullet points)
   - How to test it
   - Which issue it closes: `Closes #N`

7. **CI must pass.** GitHub Actions runs `python manage.py check` and `pytest tests/` on every PR. Fix any failures before requesting review.

---

## Project Structure Reference

```
bounty_hunter/
├── models/models.py       — All data models (Bounty, Evaluation, Solution, Submission, Earning)
├── scouts/                — Platform scrapers
├── analyst/scorer.py      — ROI scoring + AI difficulty estimation
├── picker/tasks.py        — Target selection
├── solver/                — AI coding agent (WIP)
├── submitter/             — PR creation (WIP)
├── tracker/               — PR monitoring (WIP)
├── api/                   — REST API (ViewSets, serializers, routes)
└── utils/ai_client.py     — Multi-provider AI client
```

For architecture details, see [docs/architecture.md](docs/architecture.md).

For all configuration variables, see [docs/configuration.md](docs/configuration.md).

For the REST API reference, see [docs/api.md](docs/api.md).

---

## Getting Help

- Open a GitHub issue for bugs or feature requests
- Check `CLAUDE.md` in the repo root for project context and debugging tips
- Run `python manage.py check` first — it catches most Django configuration issues
