"""Tests for GuardrailChecker and ReputationTracker."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_bounty():
    b = MagicMock()
    b.id = 1
    b.platform = "github"
    b.repo_full_name = "testorg/testrepo"
    b.repo_owner = "testorg"
    b.repo_name = "testrepo"
    b.status = "in_progress"
    b.deadline = None
    b.bounty_amount_usd = Decimal("200")
    return b


@pytest.fixture
def ready_solution():
    s = MagicMock()
    s.status = "ready"
    s.all_tests_pass = True
    s.review_approved = True
    s.review_notes = "HUMAN_APPROVED — looks good"
    s.files_changed = ["src/fix.py", "tests/test_fix.py"]
    s.time_spent_hours = 2.0
    return s


@pytest.mark.django_db
class TestSolutionQuality:
    def test_blocks_if_tests_not_passing(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        ready_solution.all_tests_pass = False
        checker = GuardrailChecker()
        passed, reason = checker._check_solution_quality(mock_bounty, ready_solution)
        assert not passed
        assert "tests" in reason.lower()

    def test_blocks_if_not_reviewed(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        ready_solution.review_approved = False
        checker = GuardrailChecker()
        passed, reason = checker._check_solution_quality(mock_bounty, ready_solution)
        assert not passed
        assert "review" in reason.lower()

    def test_blocks_if_wrong_status(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        ready_solution.status = "coding"
        checker = GuardrailChecker()
        passed, reason = checker._check_solution_quality(mock_bounty, ready_solution)
        assert not passed

    def test_passes_ready_solution(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        checker = GuardrailChecker()
        passed, _ = checker._check_solution_quality(mock_bounty, ready_solution)
        assert passed


@pytest.mark.django_db
class TestHumanReviewQuota:
    def test_blocks_when_below_threshold(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        ready_solution.review_notes = ""  # no HUMAN_APPROVED
        checker = GuardrailChecker()
        passed, reason = checker._check_human_review_quota(mock_bounty, ready_solution)
        # 0 submissions in DB < 20 threshold, and no HUMAN_APPROVED → blocked
        assert not passed

    def test_passes_with_human_approved_note(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        ready_solution.review_notes = "HUMAN_APPROVED"
        checker = GuardrailChecker()
        passed, _ = checker._check_human_review_quota(mock_bounty, ready_solution)
        assert passed


@pytest.mark.django_db
class TestRateLimit:
    def test_passes_with_no_submissions(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        checker = GuardrailChecker()
        passed, _ = checker._check_rate_limit(mock_bounty, ready_solution)
        assert passed


@pytest.mark.django_db
class TestBountyStatus:
    def test_blocks_already_submitted(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        mock_bounty.status = "submitted"
        checker = GuardrailChecker()
        passed, reason = checker._check_bounty_still_open(mock_bounty, ready_solution)
        assert not passed
        assert "terminal" in reason.lower() or "status" in reason.lower()

    def test_passes_in_progress(self, mock_bounty, ready_solution):
        from bounty_hunter.utils.guardrails import GuardrailChecker
        mock_bounty.status = "in_progress"
        checker = GuardrailChecker()
        passed, _ = checker._check_bounty_still_open(mock_bounty, ready_solution)
        assert passed


@pytest.mark.django_db
def test_full_check_blocked_no_human_approval(mock_bounty, ready_solution):
    from bounty_hunter.utils.guardrails import GuardrailChecker
    ready_solution.review_notes = ""
    checker = GuardrailChecker()
    allowed, reason = checker.check_submission_allowed(mock_bounty, ready_solution)
    assert not allowed


@pytest.mark.django_db
def test_reputation_tracker_new_repo():
    from bounty_hunter.utils.guardrails import ReputationTracker
    tracker = ReputationTracker()
    stats = tracker.get_repo_stats("testorg/testrepo")
    assert stats["total"] == 0
    assert not tracker.is_repo_blacklisted("testorg/testrepo")
