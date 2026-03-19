"""
Submitter Agent — creates PRs for solved bounties and claims rewards.
Pipeline: guardrails check → branch → PR body → gh CLI → comment → record Submission → update status
"""
import logging
import re
import subprocess

from django.conf import settings
from django.utils import timezone

try:
    from bounty_hunter.utils.guardrails import GuardrailChecker
except ImportError:
    GuardrailChecker = None

logger = logging.getLogger(__name__)


class SubmitterAgent:
    def __init__(self):
        self.config = settings.BOUNTY_HUNTER

    def submit(self, solution):
        """Full submission pipeline. Returns Submission or None if blocked."""
        from bounty_hunter.models.models import Submission, BountyStatus

        bounty = solution.bounty

        # Guardrails
        if GuardrailChecker is not None:
            checker = GuardrailChecker()
            allowed, reason = checker.check_submission_allowed(bounty, solution)
            if not allowed:
                logger.warning("submitter: blocked — %s (bounty %d)", reason, bounty.id)
                return None
        else:
            logger.warning("submitter: guardrails not available, proceeding")

        branch = self._make_branch_name(bounty)
        title = self._make_pr_title(bounty)
        body = self._make_pr_body(bounty, solution)

        pr_url, pr_number = self._open_pr(bounty.repo_full_name, branch, title, body)
        if not pr_url:
            logger.error("submitter: PR creation failed for bounty %d", bounty.id)
            return None

        sub = Submission.objects.create(
            bounty=bounty,
            solution=solution,
            pr_url=pr_url,
            pr_number=pr_number,
            pr_status=Submission.PRStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )
        bounty.status = BountyStatus.SUBMITTED
        bounty.save(update_fields=["status", "updated_at"])
        logger.info(
            "submitter: PR #%d created for bounty %d — %s",
            pr_number,
            bounty.id,
            pr_url,
        )
        return sub

    def _make_branch_name(self, bounty):
        slug = re.sub(r"[^a-z0-9]+", "-", bounty.title.lower())[:50].strip("-")
        return (
            f"fix/issue-{bounty.issue_number}-{slug}"
            if bounty.issue_number
            else f"fix/{slug}"
        )

    def _make_pr_title(self, bounty):
        return f"fix: {bounty.title[:72]}"

    def _make_pr_body(self, bounty, solution):
        files_list = "\n".join(f"- `{f}`" for f in (solution.files_changed or []))
        ref = f"Closes #{bounty.issue_number}" if bounty.issue_number else ""
        return (
            f"## Summary\n{solution.diff_summary or 'See implementation plan below.'}\n\n"
            f"## Files Changed\n{files_list}\n\n"
            f"## Implementation Plan\n{solution.implementation_plan or 'N/A'}\n\n"
            f"{ref}\n\n"
            "---\n"
            "*Submitted by [Bounty Hunter Agent](https://github.com/ujjwalgupta983/bounty-hunter-agent)"
            " — automated bounty solver*"
        )

    def _open_pr(self, repo_full_name, branch, title, body):
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    repo_full_name,
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error("submitter._open_pr: gh error: %s", result.stderr)
                return None, None
            pr_url = result.stdout.strip()
            pr_number = int(pr_url.rstrip("/").split("/")[-1])
            return pr_url, pr_number
        except Exception as exc:
            logger.exception("submitter._open_pr: exception: %s", exc)
            return None, None
