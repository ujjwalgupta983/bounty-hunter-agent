"""
Tracker agent — monitors open PRs, responds to review comments,
and updates bounty/submission status based on GitHub feedback.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.tracker.tasks.check_all_prs")
def check_all_prs():
    """
    Periodic task: check status of all open PR submissions.

    For each SUBMITTED bounty:
    - Poll GitHub PR state
    - Update Submission.pr_status
    - If merged → update Bounty.status to MERGED
    - If changes_requested → trigger review response (TODO)

    WIP — full implementation in Issue #4.
    """
    from bounty_hunter.models.models import Submission

    open_submissions = Submission.objects.filter(
        pr_status__in=[
            Submission.PRStatus.SUBMITTED,
            Submission.PRStatus.REVIEW_REQUESTED,
            Submission.PRStatus.CHANGES_REQUESTED,
        ]
    ).select_related("bounty")

    count = open_submissions.count()
    if count == 0:
        logger.info("tracker.check_all_prs: no open submissions to check")
        return {"checked": 0}

    logger.info("tracker.check_all_prs: checking %d open submissions", count)

    checked = 0
    errors = []

    for submission in open_submissions:
        try:
            _check_pr(submission)
            checked += 1
        except Exception as exc:
            logger.exception(
                "tracker.check_all_prs: error checking PR #%d for bounty %d",
                submission.pr_number,
                submission.bounty_id,
            )
            errors.append({"submission_id": submission.id, "error": str(exc)})

    logger.info("tracker.check_all_prs: done. checked=%d errors=%d", checked, len(errors))
    return {"checked": checked, "errors": errors}


def _check_pr(submission):
    """Check a single PR's status via GitHub API and update the DB record."""
    from django.conf import settings
    from django.utils import timezone
    from github import Github, GithubException

    from bounty_hunter.models.models import BountyStatus

    token = settings.BOUNTY_HUNTER.get("GITHUB_TOKEN", "")
    if not token:
        logger.warning("tracker._check_pr: no GITHUB_TOKEN configured, skipping")
        return

    gh = Github(token)
    repo = gh.get_repo(submission.bounty.repo_full_name)

    try:
        pr = repo.get_pull(submission.pr_number)
    except GithubException as exc:
        logger.warning(
            "tracker._check_pr: could not fetch PR #%d from %s: %s",
            submission.pr_number,
            submission.bounty.repo_full_name,
            exc,
        )
        return

    # Map GitHub PR state to our PRStatus choices
    new_status = submission.pr_status
    if pr.merged:
        new_status = submission.PRStatus.MERGED
    elif pr.state == "closed":
        new_status = submission.PRStatus.CLOSED
    elif pr.state == "open":
        reviews = list(pr.get_reviews())
        if reviews:
            latest = reviews[-1]
            if latest.state == "APPROVED":
                new_status = submission.PRStatus.APPROVED
            elif latest.state == "CHANGES_REQUESTED":
                new_status = submission.PRStatus.CHANGES_REQUESTED

    if new_status != submission.pr_status:
        logger.info(
            "tracker._check_pr: PR #%d status changed %s → %s",
            submission.pr_number,
            submission.pr_status,
            new_status,
        )
        submission.pr_status = new_status
        if new_status == submission.PRStatus.MERGED:
            submission.merged_at = timezone.now()
            # Promote bounty status
            submission.bounty.status = BountyStatus.MERGED
            submission.bounty.save(update_fields=["status", "updated_at"])
        submission.save(update_fields=["pr_status", "merged_at", "last_checked_at"])
    else:
        # Just bump last_checked_at
        submission.save(update_fields=["last_checked_at"])
