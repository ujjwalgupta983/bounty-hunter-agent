"""Celery tasks for the submitter agent."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.submitter.tasks.submit_ready_solutions")
def submit_ready_solutions():
    """Submit all READY solutions that haven't been submitted yet."""
    from bounty_hunter.models.models import Solution
    from bounty_hunter.submitter.submitter import SubmitterAgent

    ready = Solution.objects.filter(
        status=Solution.SolverStatus.READY,
        bounty__submissions__isnull=True,
    ).select_related("bounty")

    agent = SubmitterAgent()
    submitted = 0
    errors = []
    for sol in ready:
        try:
            result = agent.submit(sol)
            if result:
                submitted += 1
        except Exception as exc:
            logger.exception(
                "submit_ready_solutions: error for solution %d: %s", sol.id, exc
            )
            errors.append({"solution_id": sol.id, "error": str(exc)})

    return {"submitted": submitted, "errors": errors}


@shared_task(name="bounty_hunter.submitter.tasks.submit_solution")
def submit_solution(solution_id):
    """Submit a single solution by ID."""
    from bounty_hunter.models.models import Solution
    from bounty_hunter.submitter.submitter import SubmitterAgent

    try:
        sol = Solution.objects.select_related("bounty").get(id=solution_id)
    except Solution.DoesNotExist:
        logger.warning("submit_solution: solution %d not found", solution_id)
        return {"error": "not_found"}

    agent = SubmitterAgent()
    result = agent.submit(sol)
    return {"submitted": bool(result), "pr_url": result.pr_url if result else None}
