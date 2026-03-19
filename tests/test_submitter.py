"""Tests for submitter agent."""
import re
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_solution(evaluated_bounty):
    from bounty_hunter.models.models import Solution

    return Solution.objects.create(
        bounty=evaluated_bounty,
        status=Solution.SolverStatus.READY,
        all_tests_pass=True,
        review_approved=True,
        files_changed=["src/auth.py", "tests/test_auth.py"],
        diff_summary="Added unicode normalization in password validation",
        implementation_plan="Fix the auth validator to handle special chars",
    )


@pytest.mark.django_db
class TestBranchNaming:
    def test_branch_name_format(self, mock_solution):
        from bounty_hunter.submitter.submitter import SubmitterAgent

        agent = SubmitterAgent()
        branch = agent._make_branch_name(mock_solution.bounty)
        assert branch.startswith("fix/issue-")
        assert len(branch) <= 100

    def test_branch_name_slugified(self, mock_solution):
        from bounty_hunter.submitter.submitter import SubmitterAgent

        agent = SubmitterAgent()
        branch = agent._make_branch_name(mock_solution.bounty)
        assert re.match(r"^[a-z0-9/\-]+$", branch)


@pytest.mark.django_db
class TestPRBody:
    def test_pr_body_contains_issue_ref(self, mock_solution):
        from bounty_hunter.submitter.submitter import SubmitterAgent

        agent = SubmitterAgent()
        body = agent._make_pr_body(mock_solution.bounty, mock_solution)
        assert "Closes #1" in body

    def test_pr_body_contains_files(self, mock_solution):
        from bounty_hunter.submitter.submitter import SubmitterAgent

        agent = SubmitterAgent()
        body = agent._make_pr_body(mock_solution.bounty, mock_solution)
        assert "src/auth.py" in body

    def test_pr_body_contains_attribution(self, mock_solution):
        from bounty_hunter.submitter.submitter import SubmitterAgent

        agent = SubmitterAgent()
        body = agent._make_pr_body(mock_solution.bounty, mock_solution)
        assert "Bounty Hunter Agent" in body


@pytest.mark.django_db
def test_submit_blocked_by_guardrails(mock_solution):
    """Submit returns None when guardrails block."""
    from bounty_hunter.submitter.submitter import SubmitterAgent

    agent = SubmitterAgent()
    with patch(
        "bounty_hunter.submitter.submitter.GuardrailChecker.check_submission_allowed",
        return_value=(False, "Human review required"),
    ):
        result = agent.submit(mock_solution)
    assert result is None


@pytest.mark.django_db
def test_submit_task_no_ready_solutions():
    from bounty_hunter.submitter.tasks import submit_ready_solutions

    result = submit_ready_solutions()
    assert result["submitted"] == 0
