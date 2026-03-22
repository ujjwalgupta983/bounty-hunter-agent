"""Celery tasks for bounty analysis."""
import logging
from celery import shared_task

from django.db.models import Q

from bounty_hunter.models.models import Bounty, BountyStatus

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.analyst.tasks.evaluate_new_bounties")
def evaluate_new_bounties():
    """Evaluate all newly discovered bounties."""
    from bounty_hunter.analyst.scorer import BountyAnalyst

    analyst = BountyAnalyst()
    new_bounties = Bounty.objects.filter(status=BountyStatus.DISCOVERED)
    count = 0

    for bounty in new_bounties:
        try:
            analyst.evaluate(bounty)
            count += 1
        except Exception as e:
            logger.error(f"Failed to evaluate bounty {bounty.id}: {e}")

    logger.info(f"Evaluated {count} new bounties")

    # Trigger picker after evaluation
    from bounty_hunter.picker.tasks import pick_targets
    pick_targets.delay()

    return {"evaluated": count}


@shared_task(name="bounty_hunter.analyst.tasks.rescore_stale_bounties")
def rescore_stale_bounties():
    """Re-evaluate bounties that haven't been scored in 7+ days."""
    from django.utils import timezone
    from datetime import timedelta
    from bounty_hunter.analyst.scorer import BountyAnalyst

    analyst = BountyAnalyst()
    stale_cutoff = timezone.now() - timedelta(days=7)

    stale = Bounty.objects.filter(
        Q(status=BountyStatus.EVALUATED, evaluation__evaluated_at__lt=stale_cutoff) |
        Q(status=BountyStatus.EVALUATED, evaluation__needs_reeval=True)
    )

    count = 0
    for bounty in stale:
        try:
            bounty.evaluation.delete()
            bounty.status = BountyStatus.DISCOVERED
            bounty.save()
            analyst.evaluate(bounty)
            count += 1
        except Exception as e:
            logger.error(f"Failed to rescore bounty {bounty.id}: {e}")

    logger.info(f"Rescored {count} stale bounties")
    return {"rescored": count}
