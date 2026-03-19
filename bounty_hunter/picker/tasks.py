"""Celery tasks for bounty picking/targeting."""
import logging
from celery import shared_task
from django.conf import settings

from bounty_hunter.models.models import Bounty, BountyStatus

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.picker.tasks.pick_targets")
def pick_targets():
    """Select top bounties to work on based on ROI score and capacity."""
    max_concurrent = settings.BOUNTY_HUNTER["MAX_CONCURRENT_SOLVERS"]
    min_roi = settings.BOUNTY_HUNTER["MIN_ROI_SCORE"]

    # How many slots are available?
    active_count = Bounty.objects.filter(
        status__in=[BountyStatus.TARGETED, BountyStatus.IN_PROGRESS]
    ).count()
    available_slots = max_concurrent - active_count

    if available_slots <= 0:
        logger.info(f"No available slots ({active_count}/{max_concurrent} active)")
        return {"picked": 0, "reason": "at capacity"}

    # Get top evaluated bounties by ROI
    candidates = (
        Bounty.objects
        .filter(status=BountyStatus.EVALUATED)
        .exclude(evaluation__auto_rejected=True)
        .filter(evaluation__roi_score__gte=min_roi)
        .order_by("-evaluation__roi_score")
        [:available_slots]
    )

    picked = 0
    for bounty in candidates:
        bounty.status = BountyStatus.TARGETED
        bounty.save()
        picked += 1
        logger.info(
            f"Targeted: ${bounty.bounty_amount_usd} ROI:{bounty.evaluation.roi_score:.1f} "
            f"— {bounty.title[:60]}"
        )

        # Notify via Telegram
        try:
            from bounty_hunter.utils.notifications import notifier
            notifier.notify_targeted(bounty, bounty.evaluation)
        except Exception:
            pass

    logger.info(f"Picked {picked} new targets")
    return {"picked": picked}
