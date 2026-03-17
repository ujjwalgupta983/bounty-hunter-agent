"""
Celery tasks for bounty scouting.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="bounty_hunter.scouts.tasks.run_full_scan")
def run_full_scan(self):
    """Run all scouts and aggregate results."""
    from bounty_hunter.scouts.github_scout import GitHubScout
    from bounty_hunter.scouts.algora_scout import AlgoraScout

    results = {}

    # GitHub Scout
    try:
        github_scout = GitHubScout()
        results["github"] = github_scout.scan()
        logger.info(f"GitHub scan: {results['github']}")
    except Exception as e:
        logger.error(f"GitHub scout failed: {e}")
        results["github"] = {"error": str(e)}

    # Algora Scout
    try:
        algora_scout = AlgoraScout()
        results["algora"] = algora_scout.scan()
        logger.info(f"Algora scan: {results['algora']}")
    except Exception as e:
        logger.error(f"Algora scout failed: {e}")
        results["algora"] = {"error": str(e)}

    # Trigger evaluation for new bounties
    from bounty_hunter.analyst.tasks import evaluate_new_bounties
    evaluate_new_bounties.delay()

    return results


@shared_task(name="bounty_hunter.scouts.tasks.scan_github")
def scan_github():
    """Run GitHub scout only."""
    from bounty_hunter.scouts.github_scout import GitHubScout
    return GitHubScout().scan()


@shared_task(name="bounty_hunter.scouts.tasks.scan_algora")
def scan_algora():
    """Run Algora scout only."""
    from bounty_hunter.scouts.algora_scout import AlgoraScout
    return AlgoraScout().scan()
