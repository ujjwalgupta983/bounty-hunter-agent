"""Tests for solver agent."""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal


@pytest.mark.django_db
def test_solve_targeted_bounties_empty():
    from bounty_hunter.solver.tasks import solve_targeted_bounties
    result = solve_targeted_bounties()
    assert result["solved"] == 0


@pytest.mark.django_db
def test_solve_bounty_not_found():
    from bounty_hunter.solver.tasks import solve_bounty
    result = solve_bounty(99999)
    assert "error" in result


@pytest.mark.django_db
def test_solver_explore(evaluated_bounty):
    from bounty_hunter.solver.solver import SolverAgent
    from bounty_hunter.models.models import Solution
    agent = SolverAgent()
    sol = Solution.objects.create(
        bounty=evaluated_bounty,
        status=Solution.SolverStatus.EXPLORING,
        max_iterations=1,
    )
    # Should not raise even without GitHub token
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("no network")
        context = agent._explore(evaluated_bounty, sol)
    assert evaluated_bounty.title in context


@pytest.mark.django_db
def test_solver_branch_name_in_submitter(evaluated_bounty):
    """Solver creates solution, submitter uses it for branch name."""
    from bounty_hunter.submitter.submitter import SubmitterAgent
    from bounty_hunter.models.models import Solution
    sol = Solution.objects.create(
        bounty=evaluated_bounty,
        status=Solution.SolverStatus.READY,
        all_tests_pass=True,
        review_approved=True,
        files_changed=["fix.py"],
    )
    agent = SubmitterAgent()
    branch = agent._make_branch_name(evaluated_bounty)
    assert "issue-1" in branch
