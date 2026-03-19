"""Tracker Agent — monitors submitted PRs, detects state changes, records earnings."""
import logging
import datetime
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.tracker.tasks.check_all_prs")
def check_all_prs():
    from bounty_hunter.models.models import Submission
    open_subs = Submission.objects.filter(
        pr_status__in=["submitted", "review_requested", "changes_requested", "approved"]
    ).select_related("bounty")
    count = open_subs.count()
    if count == 0:
        return {"checked": 0}
    logger.info("tracker: checking %d open PRs", count)
    checked, errors = 0, []
    for sub in open_subs:
        try:
            _check_pr(sub)
            checked += 1
        except Exception as exc:
            errors.append({"id": sub.id, "error": str(exc)})
            logger.exception("tracker: error on submission %d", sub.id)
    return {"checked": checked, "errors": errors}


def _check_pr(submission):
    from django.conf import settings
    from github import Github, GithubException
    from bounty_hunter.models.models import BountyStatus, Submission as Sub
    token = settings.BOUNTY_HUNTER.get("GITHUB_TOKEN", "")
    if not token:
        return
    gh = Github(token)
    try:
        repo = gh.get_repo(submission.bounty.repo_full_name)
        pr = repo.get_pull(submission.pr_number)
    except GithubException as exc:
        logger.warning("tracker: cannot get PR #%d: %s", submission.pr_number, exc)
        return
    new_status = submission.pr_status
    if pr.merged:
        new_status = Sub.PRStatus.MERGED
    elif pr.state == "closed":
        new_status = Sub.PRStatus.CLOSED
    elif pr.state == "open":
        reviews = list(pr.get_reviews())
        if reviews:
            last = reviews[-1]
            if last.state == "APPROVED":
                new_status = Sub.PRStatus.APPROVED
            elif last.state == "CHANGES_REQUESTED":
                new_status = Sub.PRStatus.CHANGES_REQUESTED
                submission.review_comments = [{"author": r.user.login, "body": r.body} for r in reviews if r.body]
    if new_status != submission.pr_status:
        logger.info("tracker: PR #%d %s → %s", submission.pr_number, submission.pr_status, new_status)
        submission.pr_status = new_status
        if new_status == Sub.PRStatus.MERGED:
            submission.merged_at = timezone.now()
            submission.bounty.status = BountyStatus.MERGED
            submission.bounty.save(update_fields=["status", "updated_at"])
            record_earning.delay(submission.id)
            try:
                from bounty_hunter.utils.notifications import notifier
                notifier.notify_pr_merged(submission.bounty, submission)
            except Exception:
                pass
        elif new_status == Sub.PRStatus.CHANGES_REQUESTED:
            try:
                from bounty_hunter.utils.notifications import notifier
                notifier.notify_pr_needs_attention(submission.bounty, submission, "Changes requested")
            except Exception:
                pass
    submission.save(update_fields=["pr_status", "merged_at", "last_checked_at", "review_comments"])


@shared_task(name="bounty_hunter.tracker.tasks.record_earning")
def record_earning(submission_id: int):
    from bounty_hunter.models.models import Submission, Earning
    from decimal import Decimal
    try:
        sub = Submission.objects.select_related("bounty").get(id=submission_id)
    except Submission.DoesNotExist:
        logger.error("tracker: submission %d not found", submission_id)
        return
    if Earning.objects.filter(submission=sub).exists():
        return
    bounty = sub.bounty
    gross = float(bounty.bounty_amount_usd)
    fee = gross * 0.10
    agent_cost = 0.0
    try:
        agent_cost = float(sub.solution.agent_cost_usd)
    except Exception:
        pass
    net = gross - fee - agent_cost
    merged = sub.merged_at or timezone.now()
    hours = max((merged - bounty.discovered_at).total_seconds() / 3600, 0.5)
    earning = Earning.objects.create(
        bounty=bounty, submission=sub,
        amount_usd=Decimal(str(round(gross, 2))),
        platform_fee_usd=Decimal(str(round(fee, 2))),
        agent_cost_usd=Decimal(str(round(agent_cost, 2))),
        net_earning_usd=Decimal(str(round(net, 2))),
        total_time_hours=round(hours, 2),
        effective_hourly_rate=Decimal(str(round(net / hours, 2))),
    )
    bounty.status = "paid"
    bounty.save(update_fields=["status", "updated_at"])
    logger.info("tracker: earning $%.2f recorded for bounty %d", net, bounty.id)
    try:
        from bounty_hunter.utils.notifications import notifier
        notifier.notify_payment_received(earning)
    except Exception:
        pass


@shared_task(name="bounty_hunter.tracker.tasks.ping_stale_prs")
def ping_stale_prs():
    from bounty_hunter.models.models import Submission
    cutoff = timezone.now() - datetime.timedelta(days=7)
    stale = Submission.objects.filter(
        pr_status__in=["submitted", "review_requested"],
        last_checked_at__lt=cutoff,
    )
    count = stale.count()
    for s in stale:
        logger.warning("tracker: stale PR #%d open 7+ days: %s", s.pr_number, s.pr_url)
    return {"stale": count}
