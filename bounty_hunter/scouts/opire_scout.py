"""
Opire Scout — Scrapes opire.dev for open bounties.

Opire is a bounty platform where maintainers post rewards on GitHub issues.
Tries multiple API endpoints, then falls back to scraping https://opire.dev/home.
"""
import re
import logging
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings
from django.utils import timezone

from bounty_hunter.models.models import Bounty, Platform, ScanLog, PaymentMethod

logger = logging.getLogger(__name__)

# Known API endpoint candidates (Opire has changed these before)
OPIRE_API_URLS = [
    "https://api.opire.dev/v1/rewards",
    "https://api.opire.dev/rewards",
    "https://app.opire.dev/api/rewards",
]
OPIRE_WEB_URL = "https://opire.dev"


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
        """Try multiple API endpoints, then fall back to scraping."""
        # Try each known API URL
        for api_url in OPIRE_API_URLS:
            try:
                bounties = self._fetch_from_api(api_url)
                if bounties:
                    logger.info(f"Opire API ({api_url}) returned {len(bounties)} bounties")
                    return bounties
            except Exception as e:
                logger.debug(f"Opire API {api_url} failed: {e}")
                continue

        # Fall back to scraping
        logger.info("All Opire API endpoints failed, falling back to scraping")
        try:
            bounties = self._scrape_web_page()
            logger.info(f"Opire scraper returned {len(bounties)} bounties")
            return bounties
        except Exception as e:
            logger.error(f"Opire scraping also failed: {e}")

        return []

    def _fetch_from_api(self, api_url: str) -> list:
        """Fetch bounties from an Opire API endpoint."""
        with httpx.Client(timeout=30) as client:
            response = client.get(api_url, params={"status": "open"})
            if response.status_code == 404:
                raise ValueError(f"Opire API endpoint not found: {api_url}")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return data.get("data", data.get("rewards", data.get("items", [])))

    def _scrape_web_page(self) -> list:
        """Scrape https://opire.dev for bounties."""
        from bs4 import BeautifulSoup

        bounties = []

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # Try the home page and dedicated rewards pages
            for path in ["/home", "/", "/rewards"]:
                try:
                    response = client.get(f"{OPIRE_WEB_URL}{path}")
                    if response.status_code == 200:
                        break
                except Exception:
                    continue
            else:
                logger.error("Could not reach any Opire page")
                return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Try multiple selectors for bounty cards
        cards = (
            soup.select("[data-reward-id]")
            or soup.select(".reward-card")
            or soup.select("article")
            or soup.select("div[class*='reward']")
            or soup.select("div[class*='bounty']")
            or soup.select("tr")
        )

        for card in cards:
            try:
                title_el = card.select_one(
                    "h3, h4, .title, a[href*='github.com'], a[href*='/issues/']"
                )
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                card_text = card.get_text()

                # Extract amount
                amount_match = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', card_text)
                if not amount_match:
                    # Try EUR or plain number near "reward"/"bounty"
                    amount_match = re.search(r'([\d,]+(?:\.\d{2})?)\s*(?:USD|EUR|\$)', card_text)
                if not amount_match:
                    continue
                amount = float(amount_match.group(1).replace(",", ""))

                # Extract GitHub link
                link_el = card.select_one("a[href*='github.com']")
                link = link_el.get("href", "") if link_el else ""

                repo_owner, repo_name, issue_number = self._parse_github_url(link)

                # Status detection
                status = "open"
                lower_text = card_text.lower()
                if "closed" in lower_text or "completed" in lower_text:
                    status = "closed"

                if status != "open":
                    continue

                external_id = (
                    f"opire-{repo_owner}/{repo_name}#{issue_number}"
                    if issue_number
                    else f"opire-{title[:50]}"
                )

                bounties.append({
                    "title": title,
                    "amount": amount,
                    "repo_owner": repo_owner,
                    "repo_name": repo_name,
                    "issue_number": issue_number,
                    "url": link,
                    "external_id": external_id,
                    "status": status,
                })

            except Exception as e:
                logger.debug(f"Failed to parse Opire card: {e}")
                continue

        return bounties

    def _process_bounty(self, bounty_data: dict) -> str:
        """Normalise and upsert one bounty. Returns 'new', 'updated', or 'skipped'."""
        amount = self._extract_amount(bounty_data)
        if amount is None or amount < self.min_bounty:
            return "skipped"

        external_id = str(bounty_data.get("id") or bounty_data.get("external_id") or "")
        if not external_id:
            return "skipped"

        # Issue URL — top-level "url" field on Opire API items
        url = bounty_data.get("url") or bounty_data.get("issue_url") or ""

        # Repo info — prefer project.url (Opire API), fall back to parsing issue URL
        project = bounty_data.get("project") or {}
        project_url = project.get("url", "")
        repo_owner = bounty_data.get("repo_owner") or bounty_data.get("repoOwner", "")
        repo_name = bounty_data.get("repo_name") or bounty_data.get("repoName", "")
        if not repo_owner and project_url and "github.com/" in project_url:
            repo_owner, repo_name, _ = self._parse_github_url(project_url)
        if not repo_owner and "github.com/" in url:
            repo_owner, repo_name, _ = self._parse_github_url(url)

        issue_number = bounty_data.get("issue_number") or bounty_data.get("issueNumber")
        if not issue_number and "github.com/" in url:
            _, _, issue_number = self._parse_github_url(url)

        title = (bounty_data.get("title") or bounty_data.get("issue", {}).get("title", ""))[:500]
        description = bounty_data.get("description") or bounty_data.get("body", "")

        source_url = url or OPIRE_WEB_URL
        repo_url = f"https://github.com/{repo_owner}/{repo_name}" if repo_owner else source_url

        # Detect payment method (default stripe for Opire)
        combined_text = f"{title} {description}".lower()
        payment_method = PaymentMethod.STRIPE  # Opire default
        if any(kw in combined_text for kw in ("usdc", "eth", "crypto", "token")):
            payment_method = PaymentMethod.CRYPTO
        elif any(kw in combined_text for kw in ("bank transfer", "wire")):
            payment_method = PaymentMethod.BANK_TRANSFER
        elif any(kw in combined_text for kw in ("paypal", "venmo")):
            payment_method = PaymentMethod.PAYPAL
        india_payable = payment_method in (PaymentMethod.BANK_TRANSFER, PaymentMethod.CRYPTO)

        defaults = {
            "title": title or f"Opire bounty {external_id}",
            "description": description,
            "source_url": source_url,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "repo_url": repo_url,
            "issue_number": issue_number,
            "bounty_amount_usd": Decimal(str(amount)),
            "payment_method": payment_method,
            "india_payable": india_payable,
        }

        bounty, created = Bounty.objects.update_or_create(
            platform=Platform.OPIRE,
            external_id=external_id,
            defaults=defaults,
        )
        return "new" if created else "updated"

    def _extract_amount(self, bounty_data: dict):
        """Extract USD amount from bounty data. Returns float or None.

        Opire API returns amounts as:
          pendingPrice: {value: <int cents>, unit: "USD_CENT"}
        Scraped/other data may use flat keys: amount, reward, price, etc.
        """
        # Opire API format: pendingPrice.value in USD cents
        pending_price = bounty_data.get("pendingPrice")
        if pending_price and isinstance(pending_price, dict):
            raw = pending_price.get("value")
            unit = pending_price.get("unit", "")
            if raw is not None:
                try:
                    cents = float(raw)
                    # Convert based on unit
                    if "CENT" in unit.upper():
                        return cents / 100
                    return cents  # assume already USD if no cents unit
                except (ValueError, TypeError):
                    pass

        # Flat key fallbacks (scraped data, other API variants)
        for key in ("amount", "reward", "price", "usd_amount", "value"):
            val = bounty_data.get(key)
            if val is not None:
                try:
                    return float(Decimal(str(val)))
                except (InvalidOperation, ValueError):
                    continue
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
