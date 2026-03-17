"""
Algora Scout — Scrapes Algora.io for open bounties.

Algora integrates with GitHub and allows bounty creation via `/bounty $amount` comments.
"""
import logging
from decimal import Decimal

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, ScanLog

logger = logging.getLogger(__name__)

ALGORA_API_BASE = "https://api.algora.io"
ALGORA_BOUNTIES_URL = "https://algora.io/bounties"


class AlgoraScout:
    """Scrapes Algora for open bounties."""

    def __init__(self):
        self.min_bounty = settings.BOUNTY_HUNTER["MIN_BOUNTY_USD"]

    def scan(self) -> dict:
        """Scan Algora for open bounties."""
        scan_log = ScanLog(platform=Platform.ALGORA)
        stats = {"found": 0, "new": 0, "updated": 0, "errors": []}

        try:
            bounties = self._fetch_bounties()

            for bounty_data in bounties:
                result = self._process_bounty(bounty_data)
                stats["found"] += 1
                if result == "new":
                    stats["new"] += 1
                elif result == "updated":
                    stats["updated"] += 1

            scan_log.bounties_found = stats["found"]
            scan_log.bounties_new = stats["new"]
            scan_log.bounties_updated = stats["updated"]
            scan_log.success = True
            scan_log.completed_at = timezone.now()
            scan_log.save()

            logger.info(
                f"Algora scan complete: {stats['found']} found, "
                f"{stats['new']} new, {stats['updated']} updated"
            )

        except Exception as e:
            error_msg = f"Algora scan failed: {str(e)}"
            logger.error(error_msg)
            scan_log.success = False
            scan_log.errors = [error_msg]
            scan_log.completed_at = timezone.now()
            scan_log.save()
            stats["errors"].append(error_msg)

        return stats

    def _fetch_bounties(self) -> list:
        """Fetch open bounties from Algora.

        Note: Algora's API may change. This uses the public bounties page
        and attempts API access. Falls back to web scraping if API is unavailable.
        """
        bounties = []

        try:
            # Try API first
            with httpx.Client(timeout=30) as client:
                response = client.get(
                    f"{ALGORA_API_BASE}/bounties",
                    params={"status": "open", "limit": 100},
                )
                if response.status_code == 200:
                    data = response.json()
                    bounties = data if isinstance(data, list) else data.get("bounties", [])
                    return bounties
        except Exception as e:
            logger.warning(f"Algora API unavailable, falling back to scraping: {e}")

        # Fallback: scrape the bounties page
        try:
            bounties = self._scrape_bounties_page()
        except Exception as e:
            logger.error(f"Algora scraping also failed: {e}")

        return bounties

    def _scrape_bounties_page(self) -> list:
        """Scrape Algora bounties page as fallback."""
        from bs4 import BeautifulSoup

        bounties = []

        with httpx.Client(timeout=30) as client:
            response = client.get(ALGORA_BOUNTIES_URL)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Parse bounty cards (structure may change)
        # This is a best-effort parser — Algora's DOM may change
        for card in soup.select("[data-bounty-id], .bounty-card, article"):
            try:
                title_el = card.select_one("h3, h4, .title, a[href*='github.com']")
                amount_el = card.select_one(".amount, .bounty-amount, [data-amount]")
                link_el = card.select_one("a[href*='github.com']")

                if not title_el or not amount_el:
                    continue

                title = title_el.get_text(strip=True)
                amount_text = amount_el.get_text(strip=True)
                link = link_el.get("href", "") if link_el else ""

                # Parse amount
                import re
                amount_match = re.search(r'\$?([\d,]+)', amount_text)
                if not amount_match:
                    continue
                amount = float(amount_match.group(1).replace(",", ""))

                # Parse GitHub link for repo info
                repo_owner, repo_name, issue_number = "", "", None
                if "github.com" in link:
                    parts = link.split("github.com/")[-1].split("/")
                    if len(parts) >= 2:
                        repo_owner = parts[0]
                        repo_name = parts[1]
                    if len(parts) >= 4 and parts[2] == "issues":
                        try:
                            issue_number = int(parts[3])
                        except ValueError:
                            pass

                bounties.append({
                    "title": title,
                    "amount": amount,
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "issue_number": issue_number,
                    "url": link,
                    "external_id": f"algora-{repo_owner}/{repo_name}#{issue_number}" if issue_number else f"algora-{title[:50]}",
                })

            except Exception as e:
                logger.debug(f"Failed to parse Algora card: {e}")
                continue

        return bounties

    def _process_bounty(self, bounty_data: dict) -> str:
        """Process a single Algora bounty. Returns 'new', 'updated', or 'skipped'."""
        # Handle both API and scraped formats
        amount = bounty_data.get("amount") or bounty_data.get("reward_amount", 0)
        if isinstance(amount, str):
            import re
            match = re.search(r'[\d,]+', amount)
            amount = float(match.group().replace(",", "")) if match else 0

        if amount < self.min_bounty:
            return "skipped"

        external_id = bounty_data.get("external_id") or bounty_data.get("id", "")
        title = bounty_data.get("title", "Unknown")
        repo_owner = bounty_data.get("repo_owner", "")
        repo_name = bounty_data.get("repo_name", "")
        issue_number = bounty_data.get("issue_number")
        url = bounty_data.get("url") or bounty_data.get("html_url", "")

        bounty, created = Bounty.objects.update_or_create(
            platform=Platform.ALGORA,
            external_id=str(external_id),
            defaults={
                "title": title[:500],
                "description": bounty_data.get("description", "")[:5000],
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "repo_url": f"https://github.com/{repo_owner}/{repo_name}" if repo_owner else "",
                "issue_number": issue_number,
                "source_url": url,
                "bounty_amount_usd": Decimal(str(amount)),
                "currency": "USD",
                "labels": bounty_data.get("labels", []),
                "language": bounty_data.get("language", ""),
            },
        )

        if created:
            logger.info(f"New Algora bounty: ${amount} — {title[:80]}")
            return "new"
        return "updated"
