import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="bounty_hunter.solver.tasks.solve_bounty")
def solve_bounty(bounty_id: int):
    """Solve a specific bounty."""
    from bounty_hunter.models.models import Bounty, BountyStatus
    from bounty_hunter.solver.solver import SolverAgent
    try:
        bounty = Bounty.objects.get(id=bounty_id, status=BountyStatus.TARGETED)
    except Bounty.DoesNotExist:
        logger.error("solver: bounty %d not found or not targeted", bounty_id)
        return {"error": "not found"}
    agent = SolverAgent()
    solution = agent.solve(bounty)
    return {"solved": bool(solution), "solution_id": solution.id if solution else None}


@shared_task(name="bounty_hunter.solver.tasks.solve_targeted_bounties")
def solve_targeted_bounties():
    """Find all TARGETED bounties and solve them."""
    from bounty_hunter.models.models import Bounty, BountyStatus
    from bounty_hunter.solver.solver import SolverAgent
    targeted = Bounty.objects.filter(status=BountyStatus.TARGETED)
    if not targeted.exists():
        return {"solved": 0}
    agent = SolverAgent()
    solved, errors = 0, []
    for bounty in targeted:
        try:
            sol = agent.solve(bounty)
            if sol:
                solved += 1
        except Exception as exc:
            errors.append({"bounty_id": bounty.id, "error": str(exc)})
    return {"solved": solved, "errors": errors}
