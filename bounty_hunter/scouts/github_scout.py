"""
GitHub Scout — Scrapes GitHub Issues for bounty-labeled issues.

Searches across all public repos for issues with bounty/reward/paid labels
and extracts bounty amounts from titles, labels, and issue bodies.
"""
import re
import logging
from decimal import Decimal
from datetime import datetime, timedelta

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, BountyStatus, ScanLog

logger = logging.getLogger(__name__)

# Labels that commonly indicate a bounty
BOUNTY_LABELS = [
    "bounty",
    "reward",
    "paid",
    "cash",
    "💰",
    "💵",
    "money",
    "sponsored",
    "funded",
]

# Search queries to find bounty issues
SEARCH_QUERIES = [
    'label:bounty state:open',
    'label:reward state:open',
    'label:paid state:open',
    '"[BOUNTY" in:title state:open',
    '"bounty" "$" in:title state:open',
    '"reward" "$" in:title state:open',
]

# Patterns that indicate non-code noise (governance, crypto rewards, proposals)
NOISE_PATTERNS = [
    r'proposal\b',
    r'paper\s*note',
    r'payment\s*inquiry',
    r'reward\s*(submission|program|proposal)',
    r'contributor\s*reward',
    r'airdrop',
    r'token\s*(sale|distribution|reward)',
    r'\bRIP-\d+\b',
    r'\bDLIP-\d+\b',
    r'consumer\s*app\s*submission',
    r'attestation\s*inspector',
]

NOISE_LABELS = ['governance', 'proposal', 'discussion', 'question', 'announcement']

CODE_SIGNALS = [
    'bug', 'fix', 'implement', 'feature', 'test', 'refactor',
    'error', 'crash', 'pull request', 'code', 'function', 'method',
    'class', 'api', 'endpoint',
]

# Regex patterns to extract dollar amounts
AMOUNT_PATTERNS = [
    r'\$\s*([\d,]+(?:\.\d{2})?)',           # $500 or $1,000 or $500.00
    r'([\d,]+(?:\.\d{2})?)\s*(?:USD|usd)',   # 500 USD
    r'bounty[:\s]*\$?([\d,]+)',              # bounty: 500 or bounty $500
    r'reward[:\s]*\$?([\d,]+)',              # reward: 500
]


class GitHubScout:
    """Scrapes GitHub for bounty issues using the Search API."""

    def __init__(self):
        self.token = settings.BOUNTY_HUNTER["GITHUB_TOKEN"]
        self.min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]
        self.max_age_days = settings.BOUNTY_HUNTER["MAX_BOUNTY_AGE_DAYS"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.base_url = "https://api.github.com"

    def scan(self) -> dict:
        """Run a full scan across all search queries. Returns scan stats."""
        scan_log = ScanLog(platform=Platform.GITHUB)
        stats = {"found": 0, "new": 0, "updated": 0, "errors": []}

        try:
            for query in SEARCH_QUERIES:
                try:
                    results = self._search_issues(query)
                    for issue_data in results:
                        result = self._process_issue(issue_data)
                        stats["found"] += 1
                        if result == "new":
                            stats["new"] += 1
                        elif result == "updated":
                            stats["updated"] += 1
                except Exception as e:
                    error_msg = f"Error searching '{query}': {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)

            scan_log.bounties_found = stats["found"]
            scan_log.bounties_new = stats["new"]
            scan_log.bounties_updated = stats["updated"]
            scan_log.errors = stats["errors"]
            scan_log.success = len(stats["errors"]) == 0
            scan_log.completed_at = timezone.now()
            scan_log.save()

            logger.info(
                f"GitHub scan complete: {stats['found']} found, "
                f"{stats['new']} new, {stats['updated']} updated"
            )

        except Exception as e:
            scan_log.success = False
            scan_log.errors = [str(e)]
            scan_log.completed_at = timezone.now()
            scan_log.save()
            raise

        return stats

    def _search_issues(self, query: str, max_pages: int = 5) -> list:
        """Search GitHub issues with pagination."""
        all_items = []
        per_page = 100

        with httpx.Client(headers=self.headers, timeout=30) as client:
            for page in range(1, max_pages + 1):
                response = client.get(
                    f"{self.base_url}/search/issues",
                    params={
                        "q": query,
                        "per_page": per_page,
                        "page": page,
                        "sort": "created",
                        "order": "desc",
                    },
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                all_items.extend(items)

                if len(items) < per_page:
                    break  # No more pages

                # Rate limit awareness
                remaining = int(response.headers.get("X-RateLimit-Remaining", 10))
                if remaining < 5:
                    logger.warning(f"GitHub rate limit low: {remaining} remaining")
                    break

        return all_items

    def _process_issue(self, issue_data: dict) -> str:
        """Process a single GitHub issue. Returns 'new', 'updated', or 'skipped'."""
        repo_url = issue_data.get("repository_url", "")
        repo_parts = repo_url.replace(f"{self.base_url}/repos/", "").split("/")

        if len(repo_parts) < 2:
            return "skipped"

        repo_owner, repo_name = repo_parts[0], repo_parts[1]
        issue_number = issue_data.get("number")
        external_id = f"{repo_owner}/{repo_name}#{issue_number}"

        # Extract bounty amount
        title = issue_data.get("title", "")
        body = issue_data.get("body", "") or ""
        labels = [l.get("name", "") for l in issue_data.get("labels", [])]

        # Filter noise: title pattern check
        for pattern in NOISE_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return "skipped"

        # Filter noise: label check
        lower_labels = [lbl.lower() for lbl in labels]
        if any(noise in lower_labels for noise in NOISE_LABELS):
            return "skipped"

        amount = self._extract_amount(title, body, labels)
        if amount is None or amount < self.min_bounty:
            return "skipped"

        # Require code signals to filter out non-engineering bounties
        if not self._has_code_signals(title, body, labels):
            return "skipped"

        # Check age
        created_at = issue_data.get("created_at")
        if created_at:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if timezone.now() - created_dt > timedelta(days=self.max_age_days):
                return "skipped"

        # Detect language from labels or repo
        language = self._detect_language(labels)

        # Count existing PRs (pull_request key present means it's a PR, not an issue)
        if issue_data.get("pull_request"):
            return "skipped"

        # Upsert bounty
        bounty, created = Bounty.objects.update_or_create(
            platform=Platform.GITHUB,
            external_id=external_id,
            defaults={
                "title": title[:500],
                "description": body[:5000],
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "repo_url": f"https://github.com/{repo_owner}/{repo_name}",
                "issue_number": issue_number,
                "source_url": issue_data.get("html_url", ""),
                "bounty_amount_usd": Decimal(str(amount)),
                "currency": "USD",
                "labels": labels,
                "language": language,
                "competitors_count": issue_data.get("comments", 0),
                "posted_at": created_at,
            },
        )

        if created:
            logger.info(f"New bounty: ${amount} — {title[:80]}")
            return "new"
        else:
            return "updated"

    def _extract_amount(self, title: str, body: str, labels: list) -> float | None:
        """Extract bounty amount from title, body, or labels."""
        text = f"{title} {body} {' '.join(labels)}"

        for pattern in AMOUNT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace(",", "")
                    amount = float(amount_str)
                    if 1 <= amount <= 1_000_000:  # Sanity check
                        return amount
                except (ValueError, IndexError):
                    continue

        return None

    def _has_code_signals(self, title: str, body: str, labels: list) -> bool:
        """Return True if at least 2 code signals are found in combined text."""
        combined = f"{title} {body} {' '.join(labels)}".lower()
        matches = sum(1 for signal in CODE_SIGNALS if signal in combined)
        return matches >= 2

    def _detect_language(self, labels: list) -> str:
        """Detect primary language from labels."""
        lang_map = {
            "python": "Python",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "rust": "Rust",
            "go": "Go",
            "golang": "Go",
            "java": "Java",
            "ruby": "Ruby",
            "c++": "C++",
            "cpp": "C++",
            "c#": "C#",
            "csharp": "C#",
            "php": "PHP",
            "swift": "Swift",
            "kotlin": "Kotlin",
            "solidity": "Solidity",
        }

        for label in labels:
            lower = label.lower().strip()
            if lower in lang_map:
                return lang_map[lower]

        return ""
