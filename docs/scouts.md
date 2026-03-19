# Scout System

Scouts are platform-specific scrapers that discover bounty issues from across the internet. Each scout runs as a Celery task and normalizes data into the `Bounty` model.

---

## Available Scouts

### GitHub Scout (`github_scout.py`)

Searches the GitHub Issues Search API for issues with bounty-related labels or keywords in the title.

**Search strategies:**
- Labels: `bounty`, `reward`, `paid`, `cash`, `💰`, `💵`, `money`, `sponsored`, `funded`
- Title patterns: `[BOUNTY`, `bounty $`, `reward $`

**Amount extraction:** Regex patterns parse dollar amounts from issue titles, labels, and bodies:
- `$500` or `$1,000.00`
- `500 USD`
- `bounty: 500` or `bounty $500`

**Rate limits:** Respects GitHub API rate limits (5,000 requests/hour for authenticated requests). The scout uses a `Bearer` token from `GITHUB_TOKEN`.

**Configuration:** `GITHUB_TOKEN` (required), `SCOUT_MIN_BOUNTY_USD`, `SCOUT_MAX_BOUNTY_AGE_DAYS`

---

### Algora Scout (`algora_scout.py`)

Queries the Algora.io platform for open bounties.

**Primary method:** Algora GraphQL API — returns structured bounty data with amounts, issue links, and reward currencies.

**Fallback method:** httpx web scraping of the Algora website — used when the API is unavailable or returns errors.

**Amount normalization:** Algora bounties may be denominated in crypto or other currencies. The scout converts all amounts to USD equivalents.

---

## Running Scouts Manually

```bash
# Run all scouts (full scan)
python manage.py scout_scan

# Run a specific platform only
python manage.py scout_scan --platform github
python manage.py scout_scan --platform algora

# Trigger a full scan via Celery (runs asynchronously)
python manage.py shell -c "from bounty_hunter.scouts.tasks import run_full_scan; run_full_scan.delay()"
```

---

## Scout Celery Tasks

| Task name | Description |
|---|---|
| `bounty_hunter.scouts.tasks.run_full_scan` | Run all scouts, then trigger evaluation |
| `bounty_hunter.scouts.tasks.scan_github` | Run GitHub scout only |
| `bounty_hunter.scouts.tasks.scan_algora` | Run Algora scout only |

The `run_full_scan` task is scheduled by Celery Beat every `SCOUT_SCAN_INTERVAL_HOURS` hours (default: 6). After all scouts complete, it automatically triggers `evaluate_new_bounties.delay()`.

---

## Scan Logs

Every scout run is recorded in the `ScanLog` model:

```python
ScanLog.objects.latest("started_at")
# <ScanLog: Scan: github @ 2026-03-19 10:00 — 42 found>
```

Fields:
- `platform` — which scout ran
- `started_at`, `completed_at` — timing
- `bounties_found` — total bounties seen
- `bounties_new` — new records created
- `bounties_updated` — existing records updated
- `errors` — list of error messages if any
- `success` — `True` unless the scan failed entirely

---

## How to Add a New Scout

Follow these steps to add support for a new bounty platform.

### Step 1: Create the scout module

Create `bounty_hunter/scouts/newplatform_scout.py`:

```python
"""
NewPlatform Scout — scrapes NewPlatform.io for bounties.
"""
import logging
from decimal import Decimal

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, BountyStatus, ScanLog

logger = logging.getLogger(__name__)


class NewPlatformScout:
    """Scrapes NewPlatform.io for open bounties."""

    BASE_URL = "https://api.newplatform.io/v1"

    def __init__(self):
        self.api_key = settings.BOUNTY_HUNTER.get("NEWPLATFORM_API_KEY", "")
        self.min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]

    def scan(self) -> dict:
        """
        Run the full scan. Returns a summary dict:
        {"found": N, "new": M, "updated": K, "errors": [...]}
        """
        log = ScanLog.objects.create(platform=Platform.NEWPLATFORM)
        found = new = updated = 0
        errors = []

        try:
            items = self._fetch_bounties()
            for item in items:
                try:
                    bounty_data = self._normalize(item)
                    if bounty_data is None:
                        continue
                    obj, created = Bounty.objects.update_or_create(
                        platform=Platform.NEWPLATFORM,
                        external_id=bounty_data["external_id"],
                        defaults=bounty_data,
                    )
                    found += 1
                    if created:
                        new += 1
                    else:
                        updated += 1
                except Exception as e:
                    logger.warning("newplatform_scout: error processing item: %s", e)
                    errors.append(str(e))
        except Exception as e:
            logger.error("newplatform_scout: scan failed: %s", e)
            errors.append(str(e))
            log.success = False

        log.completed_at = timezone.now()
        log.bounties_found = found
        log.bounties_new = new
        log.bounties_updated = updated
        log.errors = errors
        log.save()

        return {"found": found, "new": new, "updated": updated, "errors": errors}

    def _fetch_bounties(self) -> list:
        """Fetch raw bounty data from the platform API."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = httpx.get(f"{self.BASE_URL}/bounties?state=open", headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["data"]

    def _normalize(self, item: dict) -> dict | None:
        """
        Normalize a raw API item to Bounty model fields.
        Returns None if the bounty should be skipped.
        """
        amount = Decimal(str(item.get("amount_usd", 0)))
        if amount < self.min_bounty:
            return None

        return {
            "external_id": str(item["id"]),
            "platform": Platform.NEWPLATFORM,
            "source_url": item["url"],
            "title": item["title"],
            "description": item.get("body", ""),
            "repo_owner": item["repo"]["owner"],
            "repo_name": item["repo"]["name"],
            "repo_url": item["repo"]["html_url"],
            "issue_number": item.get("issue_number"),
            "bounty_amount_usd": amount,
            "language": item["repo"].get("language", ""),
            "labels": [label["name"] for label in item.get("labels", [])],
            "competitors_count": item.get("claimants_count", 0),
            "existing_prs": item.get("pull_requests_count", 0),
            "status": BountyStatus.DISCOVERED,
        }
```

### Step 2: Add the platform to the `Platform` enum

In `bounty_hunter/models/models.py`, add your platform to the `Platform` class:

```python
class Platform(models.TextChoices):
    # ... existing platforms ...
    NEWPLATFORM = "newplatform", "NewPlatform"
```

Then create and apply a migration:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 3: Register in the full scan task

In `bounty_hunter/scouts/tasks.py`, add your scout to `run_full_scan`:

```python
@shared_task(bind=True, name="bounty_hunter.scouts.tasks.run_full_scan")
def run_full_scan(self):
    # ... existing scouts ...

    # NewPlatform Scout
    try:
        from bounty_hunter.scouts.newplatform_scout import NewPlatformScout
        newplatform_scout = NewPlatformScout()
        results["newplatform"] = newplatform_scout.scan()
        logger.info(f"NewPlatform scan: {results['newplatform']}")
    except Exception as e:
        logger.error(f"NewPlatform scout failed: {e}")
        results["newplatform"] = {"error": str(e)}

    # ...
```

Optionally, add a standalone Celery task for running this scout alone:

```python
@shared_task(name="bounty_hunter.scouts.tasks.scan_newplatform")
def scan_newplatform():
    from bounty_hunter.scouts.newplatform_scout import NewPlatformScout
    return NewPlatformScout().scan()
```

### Step 4: Add configuration

If your scout needs an API key, add it to `bounty_hunter/settings.py` in the `BOUNTY_HUNTER` dict:

```python
BOUNTY_HUNTER = {
    # ... existing keys ...
    "NEWPLATFORM_API_KEY": env("NEWPLATFORM_API_KEY", default=""),
}
```

And document it in `config/.env.example`:

```bash
NEWPLATFORM_API_KEY=your-api-key-here
```

### Step 5: Write tests

Create `tests/test_newplatform_scout.py`:

```python
"""Tests for the NewPlatform scout."""
import pytest
from unittest.mock import patch, MagicMock
from bounty_hunter.scouts.newplatform_scout import NewPlatformScout


@pytest.mark.django_db
def test_scan_creates_bounty():
    mock_items = [
        {
            "id": "abc-123",
            "url": "https://newplatform.io/issue/1",
            "title": "Fix the login bug",
            "body": "Detailed description here...",
            "amount_usd": "200",
            "repo": {
                "owner": "testorg",
                "name": "testrepo",
                "html_url": "https://github.com/testorg/testrepo",
                "language": "Python",
            },
            "labels": [],
            "claimants_count": 0,
            "pull_requests_count": 0,
        }
    ]

    with patch.object(NewPlatformScout, "_fetch_bounties", return_value=mock_items):
        scout = NewPlatformScout()
        result = scout.scan()

    assert result["new"] == 1
    assert result["found"] == 1


@pytest.mark.django_db
def test_scan_skips_below_min_bounty():
    mock_items = [
        {"id": "xyz", "url": "...", "title": "Tiny bounty", "body": "",
         "amount_usd": "5", "repo": {"owner": "a", "name": "b",
         "html_url": "https://github.com/a/b", "language": ""}, "labels": [],
         "claimants_count": 0, "pull_requests_count": 0},
    ]

    with patch.object(NewPlatformScout, "_fetch_bounties", return_value=mock_items):
        scout = NewPlatformScout()
        result = scout.scan()

    assert result["new"] == 0
```

### Step 6: Update the CLAUDE.md platform list

Add your new platform to the "Scouts" section in `CLAUDE.md` so future contributors know it exists.

---

## Scout Best Practices

- **Always handle pagination.** Most APIs return paginated results. Use `while has_more` loops with cursor or page tokens.
- **Respect rate limits.** Check `X-RateLimit-Remaining` headers. Sleep or back off when approaching limits.
- **Use `update_or_create`.** Bounties can be updated (new competitor joins, amount increased). Don't use `get_or_create` — it won't update existing records.
- **Return a summary dict.** The `scan()` method should return `{"found": N, "new": M, "updated": K, "errors": [...]}` for consistent logging.
- **Write a `ScanLog` entry.** Always create and update a `ScanLog` so operators can see scan history.
- **Never hit real APIs in tests.** Mock `_fetch_bounties()` or use `responses`/`httpretty` to intercept HTTP calls.
- **Import heavy dependencies inside methods.** Celery workers import tasks at startup. If the API client SDK is slow to import, import it inside `scan()` or `_fetch_bounties()`.
