"""
Guardrails — safety checks before submitting a PR.
"""
import logging

logger = logging.getLogger(__name__)


class GuardrailChecker:
    """Validates that a solution is safe to submit."""

    def check_submission_allowed(self, bounty, solution):
        """
        Returns (allowed: bool, reason: str).
        Fails fast on the first violated rule.
        """
        from django.conf import settings

        config = getattr(settings, "BOUNTY_HUNTER", {})

        # Rule 1: all tests must pass
        if not solution.all_tests_pass:
            return False, "Tests are not passing"

        # Rule 2: human review required for first N submissions
        human_review_threshold = config.get("SUBMITTER_HUMAN_REVIEW_FIRST_N", 20)
        if human_review_threshold > 0:
            from bounty_hunter.models.models import Submission
            total_submitted = Submission.objects.count()
            if total_submitted < human_review_threshold:
                if not getattr(solution, "review_approved", False):
                    return False, "Human review required"

        # Rule 3: bounty must not be expired/rejected
        from bounty_hunter.models.models import BountyStatus
        terminal = {BountyStatus.REJECTED, BountyStatus.ABANDONED, BountyStatus.EXPIRED}
        if bounty.status in terminal:
            return False, f"Bounty is in terminal state: {bounty.status}"

        return True, "OK"
