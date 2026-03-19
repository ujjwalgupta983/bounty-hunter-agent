"""
Guardrails for the Submitter Agent.

Enforces safety rules before any PR is submitted:
  - Human review required for the first N submissions
  - Rate limiting: max N submissions per hour per platform
  - Solution quality checks (tests pass, lint clean, review approved)
  - Auto-rejection conditions
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class GuardrailChecker:
    """Check whether a solution is allowed to be submitted as a PR."""

    def __init__(self):
        self.config = settings.BOUNTY_HUNTER
        self.human_review_first_n: int = self.config.get("HUMAN_REVIEW_FIRST_N", 20)
        self.rate_limit_per_hour: int = self.config.get("SUBMIT_RATE_LIMIT_PER_HOUR", 3)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_submission_allowed(self, bounty, solution) -> tuple[bool, str]:
        """
        Run all guardrail checks in order.

        Returns:
            (True, "") if submission is allowed.
            (False, reason) if blocked.
        """
        checks = [
            self._check_solution_quality,
            self._check_human_review_quota,
            self._check_rate_limit,
            self._check_bounty_still_open,
        ]
        for check in checks:
            allowed, reason = check(bounty, solution)
            if not allowed:
                return False, reason
        return True, ""

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_solution_quality(self, bounty, solution) -> tuple[bool, str]:
        """Guardrail 1: All tests must pass and solution must be reviewed."""
        from bounty_hunter.models.models import Solution

        if solution.status != Solution.SolverStatus.READY:
            return False, f"solution status is '{solution.status}', expected 'ready'"

        if not solution.all_tests_pass:
            return (
                False,
                "all_tests_pass is False — never submit a PR without all existing tests passing",
            )

        if not solution.review_approved:
            return False, "review_approved is False — solution has not passed internal review"

        return True, ""

    def _check_human_review_quota(self, bounty, solution) -> tuple[bool, str]:
        """
        Guardrail 2: The first HUMAN_REVIEW_FIRST_N submissions require human
        approval before the PR is opened.  If the solution's review_notes
        contain the literal string 'HUMAN_APPROVED' we treat it as approved.
        """
        from bounty_hunter.models.models import Submission

        total_submitted = Submission.objects.count()
        if total_submitted >= self.human_review_first_n:
            # Past the probationary window — no human approval needed.
            return True, ""

        # Within the probationary window — require explicit human sign-off.
        if "HUMAN_APPROVED" not in (solution.review_notes or ""):
            return (
                False,
                (
                    f"human review required for first {self.human_review_first_n} submissions "
                    f"(total so far: {total_submitted}). "
                    "Add 'HUMAN_APPROVED' to solution.review_notes to proceed."
                ),
            )
        return True, ""

    def _check_rate_limit(self, bounty, solution) -> tuple[bool, str]:
        """
        Guardrail 3: Max SUBMIT_RATE_LIMIT_PER_HOUR submissions per hour
        across all platforms.
        """
        from bounty_hunter.models.models import Submission

        one_hour_ago = timezone.now() - timedelta(hours=1)
        recent_count = Submission.objects.filter(submitted_at__gte=one_hour_ago).count()

        if recent_count >= self.rate_limit_per_hour:
            return (
                False,
                (
                    f"rate limit reached: {recent_count} submission(s) in the last hour "
                    f"(limit: {self.rate_limit_per_hour}/hr)"
                ),
            )
        return True, ""

    def _check_bounty_still_open(self, bounty, solution) -> tuple[bool, str]:
        """Guardrail 4: Don't submit if the bounty has already been claimed/closed."""
        from bounty_hunter.models.models import BountyStatus

        terminal_statuses = {
            BountyStatus.SUBMITTED,
            BountyStatus.MERGED,
            BountyStatus.PAID,
            BountyStatus.REJECTED,
            BountyStatus.ABANDONED,
            BountyStatus.EXPIRED,
        }
        if bounty.status in terminal_statuses:
            return (
                False,
                f"bounty {bounty.id} is already in terminal status '{bounty.status}'",
            )

        if bounty.deadline and bounty.deadline < timezone.now():
            return False, f"bounty {bounty.id} deadline has passed ({bounty.deadline})"

        return True, ""


class ReputationTracker:
    """Tracks submission outcomes per repo and platform to detect bad actors."""

    def get_repo_stats(self, repo_full_name: str) -> dict:
        """Returns submission stats for a given repo."""
        from bounty_hunter.models.models import Submission
        parts = repo_full_name.split("/", 1)
        owner, repo = (parts[0], parts[1]) if len(parts) == 2 else (repo_full_name, "")
        subs = Submission.objects.filter(
            bounty__repo_owner__iexact=owner,
            bounty__repo_name__iexact=repo,
        )
        total = subs.count()
        merged = subs.filter(pr_status="merged").count()
        rejected = subs.filter(pr_status__in=["rejected", "closed"]).count()
        rejection_rate = (rejected / total) if total > 0 else 0.0
        return {"total": total, "merged": merged, "rejected": rejected, "rejection_rate": rejection_rate}

    def get_platform_stats(self, platform: str) -> dict:
        """Returns submission stats for a platform."""
        from bounty_hunter.models.models import Submission
        subs = Submission.objects.filter(bounty__platform=platform)
        total = subs.count()
        merged = subs.filter(pr_status="merged").count()
        return {"total": total, "merged": merged, "win_rate": (merged / total) if total > 0 else 0.0}

    def is_repo_blacklisted(self, repo_full_name: str) -> bool:
        """True if repo has >60% rejection rate with 3+ attempts."""
        stats = self.get_repo_stats(repo_full_name)
        return stats["total"] >= 3 and stats["rejection_rate"] > 0.6
