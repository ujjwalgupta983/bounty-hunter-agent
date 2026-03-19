"""
IssueHunt Scout — Scrapes IssueHunt.io for open bounties.

IssueHunt (issuehunt.io) is a platform where repo owners fund their open GitHub
issues with USD rewards.  The public REST API returns open funded issues.

Public API: https://issuehunt.io/api/v1/issues?status=open
"""
import logging
import re
from decimal import Decimal

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, ScanLog

logger = logging.getLogger(__name__)

ISSUEHUNT_API_BASE = "https://issuehunt.io/api/v1"
ISSUEHUNT_BROWSE_URL = "https://issuehunt.io/r"


class IssueHuntScout:
    """Scrapes IssueHunt for open funded issues.

    Tries the public REST API first; falls back to scraping the browse page
    with BeautifulSoup if the API is unavailable or returns unexpected data.
    """

    def __init__(self):
        self.min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]

    def scan(self) -> dict:
        """Scan IssueHunt for open bounties.  Returns scan stats dict."""
        scan_log = ScanLog(platform=Platform.ISSUEHUNT)
        stats = {"found": 0, "new": 0, "updated": 0, "errors": []}

        try:
            bounties = self._fetch_bounties()

            for bounty_data in bounties:
                try:
                    result = self._process_bounty(bounty_data)
                    stats["found"] += 1
                    if result == "new":
                        stats["new"] += 1
                    elif result == "updated":
                        stats["updated"] += 1
                except Exception as e:
                    error_msg = f"Failed to process IssueHunt bounty: {e}"
                    logger.warning(error_msg)
                    stats["errors"].append(error_msg)

            scan_log.bounties_found = stats["found"]
            scan_log.bounties_new = stats["new"]
            scan_log.bounties_updated = stats["updated"]
            scan_log.errors = stats["errors"]
            scan_log.success = len(stats["errors"]) == 0
            scan_log.completed_at = timezone.now()
            scan_log.save()

            logger.info(
                f"IssueHunt scan complete: {stats['found']} found, "
                f"{stats['new']} new, {stats['updated']} updated"
            )

        except Exception as e:
            error_msg = f"IssueHunt scan failed: {e}"
            logger.error(error_msg)
            scan_log.success = False
            scan_log.errors = [error_msg]
            scan_log.completed_at = timezone.now()
            scan_log.save()
            stats["errors"].append(error_msg)

        return stats

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_bounties(self) -> list:
        """Fetch open bounties from IssueHunt.

        Tries the public API first; falls back to scraping if unavailable.
        """
        try:
            bounties = self._fetch_from_api()
            if bounties:
                logger.info(f"IssueHunt API returned {len(bounties)} bounties")
                return bounties
        except Exception as e:
            logger.warning(f"IssueHunt API unavailable, falling back to scraping: {e}")

        try:
            bounties = self._scrape_browse_page()
            logger.info(f"IssueHunt scraper returned {len(bounties)} bounties")
            return bounties
        except Exception as e:
            logger.error(f"IssueHunt scraping also failed: {e}")

        return []

    def _fetch_from_api(self) -> list:
        """Fetch open funded issues from the IssueHunt REST API with pagination."""
        all_bounties: list = []
        page = 1
        per_page = 50

        headers = {}
        api_key = settings.BOUNTY_HUNTER.get("ISSUEHUNT_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"token {api_key}"

        with httpx.Client(timeout=30, headers=headers) as client:
            while True:
                response = client.get(
                    f"{ISSUEHUNT_API_BASE}/issues",
                    params={"status": "open", "page": page, "per_page": per_page},
                )

                if response.status_code == 404:
                    raise ValueError("IssueHunt API endpoint not found (404)")

                response.raise_for_status()
                data = response.json()

                # Handle both array and paginated object responses
                if isinstance(data, list):
                    all_bounties.extend(data)
                    break
                else:
                    items = (
                        data.get("issues")
                        or data.get("data")
                        or data.get("items")
                        or []
                    )
                    all_bounties.extend(items)

                    total = data.get("total") or data.get("count", 0)
                    if len(all_bounties) >= total or len(items) < per_page:
                        break
                    page += 1

        return all_bounties

    def _scrape_browse_page(self) -> list:
        """Scrape the IssueHunt browse page as a fallback."""
        from bs4 import BeautifulSoup

        bounties = []

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                "https://issuehunt.io/issues",
                params={"status": "open"},
            )
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        cards = (
            soup.select("[data-issue-id]")
            or soup.select(".issue-card")
            or soup.select("article")
            or soup.select("[class*='issue']")
        )

        for card in cards:
            try:
                title_el = card.select_one("h2, h3, h4, .title, a")
                amount_el = card.select_one(
                    ".amount, [data-amount], [class*='amount'], [class*='fund'], [class*='reward']"
                )
                link_el = card.select_one("a[href*='github.com'], a[href*='issuehunt.io']")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                amount_text = amount_el.get_text(strip=True) if amount_el else card.get_text()
                amount_match = re.search(r'\$?\s*([\d,]+(?:\.\d{2})?)', amount_text)
                if not amount_match:
                    continue
                amount = float(amount_match.group(1).replace(",", ""))

                link = link_el.get("href", "") if link_el else ""
                repo_owner, repo_name, issue_number = self._parse_github_url(link)

                external_id = (
                    f"issuehunt-{repo_owner}/{repo_name}#{issue_number}"
                    if issue_number
                    else f"issuehunt-{title[:50]}"
                )

                bounties.append({
                    "title": title,
                    "amount": amount,
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "issue_number": issue_number,
                    "url": link,
                    "external_id": external_id,
                })

            except Exception as e:
                logger.debug(f"Failed to parse IssueHunt card: {e}")
                continue

        return bounties

    # ------------------------------------------------------------------
    # Data processing
    # ------------------------------------------------------------------

    def _process_bounty(self, bounty_data: dict) -> str:
        """Normalise and upsert one bounty.  Returns 'new', 'updated', or 'skipped'."""
        amount = self._extract_amount(bounty_data)
        if amount is None or amount < self.min_bounty:
            return "skipped"

        # Build external_id
        external_id = str(
            bounty_data.get("external_id")
            or bounty_data.get("id")
            or bounty_data.get("issueId")
            or ""
        )
        if not external_id:
            repo_owner = bounty_data.get("repo_owner") or bounty_data.get("repoOwner", "")
            repo_name = bounty_data.get("repo_name") or bounty_data.get("repoName", "")
            issue_num = bounty_data.get("issue_number") or bounty_data.get("number")
            external_id = (
                f"issuehunt-{repo_owner}/{repo_name}#{issue_num}"
                if issue_num
                else f"issuehunt-{bounty_data.get('title', '')[:40]}"
            )

        title = (
            bounty_data.get("title")
            or bounty_data.get("issueTitle")
            or "Unknown"
        )
        description = (
            bounty_data.get("description")
            or bounty_data.get("body")
            or bounty_data.get("issueBody", "")
        )

        # Repo info — prefer explicit fields, fall back to parsing GitHub URL
        repo_owner = (
            bounty_data.get("repo_owner")
            or bounty_data.get("repoOwner")
            or bounty_data.get("owner")
            or self._owner_from_url(bounty_data.get("url", ""))
            or self._owner_from_url(bounty_data.get("html_url", ""))
        )
        repo_name = (
            bounty_data.get("repo_name")
            or bounty_data.get("repoName")
            or bounty_data.get("repo")
            or self._name_from_url(bounty_data.get("url", ""))
            or self._name_from_url(bounty_data.get("html_url", ""))
        )
        issue_number = (
            bounty_data.get("issue_number")
            or bounty_data.get("number")
            or bounty_data.get("issueNumber")
        )
        source_url = (
            bounty_data.get("url")
            or bounty_data.get("html_url")
            or bounty_data.get("issueUrl", "")
        )
        language = (
            bounty_data.get("language")
            or bounty_data.get("primaryLanguage", "")
        )

        bounty, created = Bounty.objects.update_or_create(
            platform=Platform.ISSUEHUNT,
            external_id=external_id,
            defaults={
                "title": title[:500],
                "description": description[:5000],
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "repo_url": (
                    f"https://github.com/{repo_owner}/{repo_name}"
                    if repo_owner
                    else ""
                ),
                "issue_number": issue_number,
                "source_url": source_url,
                "bounty_amount_usd": Decimal(str(amount)),
                "currency": "USD",
                "labels": bounty_data.get("labels", []),
                "language": language,
            },
        )

        if created:
            logger.info(f"New IssueHunt bounty: ${amount} — {title[:80]}")
            return "new"
        return "updated"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_amount(self, bounty_data: dict) -> float | None:
        """Return the bounty amount as a float, or None if unparseable."""
        raw = (
            bounty_data.get("amount")
            or bounty_data.get("fund_amount")
            or bounty_data.get("fundAmount")
            or bounty_data.get("reward")
            or bounty_data.get("bountyAmount")
            or 0
        )

        if isinstance(raw, (int, float)):
            return float(raw) if raw > 0 else None

        if isinstance(raw, str):
            match = re.search(r'[\d,]+(?:\.\d+)?', raw.replace(",", ""))
            if match:
                try:
                    return float(match.group().replace(",", ""))
                except ValueError:
                    pass

        return None

    def _parse_github_url(self, url: str) -> tuple[str, str, int | None]:
        """Parse repo owner, name, and optional issue number from a GitHub URL."""
        repo_owner, repo_name, issue_number = "", "", None
        if "github.com" in url:
            parts = url.split("github.com/")[-1].rstrip("/").split("/")
            if len(parts) >= 2:
                repo_owner = parts[0]
                repo_name = parts[1]
            if len(parts) >= 4 and parts[2] == "issues":
                try:
                    issue_number = int(parts[3])
                except ValueError:
                    pass
        return repo_owner, repo_name, issue_number

    def _owner_from_url(self, url: str) -> str:
        owner, _, _ = self._parse_github_url(url)
        return owner

    def _name_from_url(self, url: str) -> str:
        _, name, _ = self._parse_github_url(url)
        return name
