"""
Telegram notifications for bounty lifecycle events.

Config (config/.env):
    TELEGRAM_BOT_TOKEN=<your-bot-token>
    TELEGRAM_CHAT_ID=<your-chat-id>

Usage:
    from bounty_hunter.utils.notifications import notifier
    notifier.notify_pr_merged(bounty, submission)

All methods return True on success, False on failure (never raise).
"""
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:

    def __init__(self):
        cfg = settings.BOUNTY_HUNTER
        self.token = cfg.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = cfg.get("TELEGRAM_CHAT_ID", "")

    def send(self, message: str) -> bool:
        """Send a Markdown message. Returns False silently if not configured."""
        if not self.token or not self.chat_id:
            logger.debug("notifications: Telegram not configured, skipping")
            return False
        try:
            url = TELEGRAM_API.format(token=self.token)
            with httpx.Client(timeout=10) as client:
                resp = client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                })
            if resp.status_code != 200:
                logger.warning("notifications: Telegram API %d: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as exc:
            logger.warning("notifications: send failed: %s", exc)
            return False

    def notify_high_value_bounty(self, bounty) -> bool:
        return self.send(
            f"🎯 *High-Value Bounty Found!*\n\n"
            f"*{bounty.title}*\n"
            f"💰 `${bounty.bounty_amount_usd}` on {bounty.platform}\n"
            f"🔗 {bounty.source_url}"
        )

    def notify_targeted(self, bounty, evaluation) -> bool:
        return self.send(
            f"🎯 *Bounty Targeted for Solving*\n\n"
            f"*{bounty.title}*\n"
            f"💰 `${bounty.bounty_amount_usd}` | ROI: `{evaluation.roi_score:.1f}` | "
            f"Est: `{evaluation.estimated_hours:.1f}h`\n"
            f"🔗 {bounty.source_url}"
        )

    def notify_pr_submitted(self, bounty, submission) -> bool:
        return self.send(
            f"📤 *PR Submitted*\n\n"
            f"*{bounty.title}*\n"
            f"💰 `${bounty.bounty_amount_usd}` on {bounty.platform}\n"
            f"🔗 {submission.pr_url}"
        )

    def notify_pr_merged(self, bounty, submission, earning=None) -> bool:
        earn_str = f"\n💸 Earned: `${earning.net_earning_usd}`" if earning else ""
        return self.send(
            f"🎉 *PR Merged — Bounty Won!*\n\n"
            f"*{bounty.title}*\n"
            f"💰 `${bounty.bounty_amount_usd}` on {bounty.platform}"
            f"{earn_str}\n"
            f"🔗 {submission.pr_url}"
        )

    def notify_pr_needs_attention(self, bounty, submission, reason: str = "") -> bool:
        return self.send(
            f"⚠️ *PR Needs Attention*\n\n"
            f"*{bounty.title}*\n"
            f"Reason: {reason or 'Changes requested'}\n"
            f"🔗 {submission.pr_url}"
        )

    def notify_pr_rejected(self, bounty, submission) -> bool:
        return self.send(
            f"❌ *PR Rejected/Closed*\n\n"
            f"*{bounty.title}*\n"
            f"💰 `${bounty.bounty_amount_usd}` on {bounty.platform}\n"
            f"🔗 {submission.pr_url}"
        )

    def notify_payment_received(self, earning) -> bool:
        return self.send(
            f"💸 *Payment Received!*\n\n"
            f"*{earning.bounty.title}*\n"
            f"Net: `${earning.net_earning_usd}` via {earning.payment_method or 'platform'}"
        )

    def notify_human_intervention_needed(self, bounty, reason: str) -> bool:
        return self.send(
            f"🚨 *Human Intervention Needed*\n\n"
            f"*{bounty.title}*\n"
            f"Reason: {reason}\n"
            f"🔗 {bounty.source_url}"
        )

    def daily_digest(self, stats: dict) -> bool:
        return self.send(
            f"📊 *Daily Bounty Report*\n\n"
            f"Scraped: `{stats.get('scraped', 0)}` | "
            f"Targeted: `{stats.get('targeted', 0)}` | "
            f"PRs Open: `{stats.get('prs_open', 0)}`\n"
            f"Confirmed: `${stats.get('confirmed_usd', 0):.2f}` | "
            f"Pending: `${stats.get('pending_usd', 0):.2f}`"
        )


# Module-level singleton
notifier = TelegramNotifier()
