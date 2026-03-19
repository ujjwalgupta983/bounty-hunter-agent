"""
Opire Scout — Scrapes opire.dev for open bounties.

Opire is a bounty platform where maintainers post rewards on GitHub issues.
API: https://api.opire.dev/v1/rewards
"""
import logging
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, ScanLog

logger = logging.getLogger(__name__)

OPIRE_API_URL = "https://api.opire.dev/v1/rewards"


class OpireScout:
    """Scrapes Opire for open bounties."""

    def __init__(self):
        self.min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]

    def scan(self) -> dict:
        """Scan Opire for open bounties. Returns scan stats dict."""
        scan_log = ScanLog(platform=Platform.OPIRE)
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
                    error_msg = f"Failed to process Opire bounty: {e}"
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
                f"Opire scan complete: {stats['found']} found, "
                f"{stats['new']} new, {stats['updated']} updated"
            )

        except Exception as e:
            error_msg = f"Opire scan failed: {e}"
            logger.error(error_msg)
            scan_log.success = False
            scan_log.errors = [error_msg]
            scan_log.completed_at = timezone.now()
            scan_log.save()

        return stats

    def _fetch_bounties(self) -> list:
        """Fetch bounties from Opire API."""
        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(OPIRE_API_URL, params={"status": "open"})
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, list) else data.get("data", data.get("rewards", []))
        except httpx.HTTPError as e:
            logger.warning("Opire API request failed: %s", e)
            return []

    def _process_bounty(self, bounty_data: dict) -> str:
        """Normalise and upsert one bounty. Returns 'new', 'updated', or 'skipped'."""
        amount = self._extract_amount(bounty_data)
        if amount is None or amount < self.min_bounty:
            return "skipped"

        external_id = str(bounty_data.get("id") or bounty_data.get("external_id") or "")
        if not external_id:
            return "skipped"

        repo_owner = bounty_data.get("repo_owner") or bounty_data.get("repoOwner", "")
        repo_name = bounty_data.get("repo_name") or bounty_data.get("repoName", "")
        issue_number = bounty_data.get("issue_number") or bounty_data.get("issueNumber")
        url = bounty_data.get("url") or bounty_data.get("issue_url") or ""
        title = (bounty_data.get("title") or bounty_data.get("issue", {}).get("title", ""))[:500]
        description = bounty_data.get("description") or bounty_data.get("body", "")

        # Derive repo_owner/name from GitHub URL if not provided directly
        if not repo_owner and "github.com/" in url:
            parts = url.replace("https://github.com/", "").split("/")
            if len(parts) >= 2:
                repo_owner = parts[0]
                repo_name = parts[1]

        source_url = url or f"https://opire.dev"
        repo_url = f"https://github.com/{repo_owner}/{repo_name}" if repo_owner else source_url

        defaults = {
            "title": title or f"Opire bounty {external_id}",
            "description": description,
            "source_url": source_url,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "repo_url": repo_url,
            "issue_number": issue_number,
            "bounty_amount_usd": Decimal(str(amount)),
        }

        bounty, created = Bounty.objects.update_or_create(
            platform=Platform.OPIRE,
            external_id=external_id,
            defaults=defaults,
        )
        return "new" if created else "updated"

    def _extract_amount(self, bounty_data: dict):
        """Extract USD amount from bounty data. Returns float or None."""
        for key in ("amount", "reward", "price", "usd_amount", "value"):
            val = bounty_data.get(key)
            if val is not None:
                try:
                    return float(Decimal(str(val)))
                except (InvalidOperation, ValueError):
                    continue
        return None
