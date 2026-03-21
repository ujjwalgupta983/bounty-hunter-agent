"""Tests for freshness bonus calculation in BountyAnalyst."""
import pytest
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone


@pytest.fixture
def analyst():
    from bounty_hunter.analyst.scorer import BountyAnalyst
    return BountyAnalyst()


@pytest.fixture
def fresh_bounty(db):
    from bounty_hunter.models.models import Bounty, Platform, BountyStatus
    return Bounty.objects.create(
        external_id="fresh-001",
        platform=Platform.GITHUB,
        source_url="https://github.com/org/repo/issues/1",
        title="Fix auth bug",
        description="The auth module fails to handle unicode passwords correctly.",
        repo_owner="org",
        repo_name="repo",
        bounty_amount_usd=Decimal("200.00"),
        status=BountyStatus.DISCOVERED,
    )


@pytest.mark.django_db
class TestFreshnessBonus:
    def test_under_6_hours_returns_1_5(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = timezone.now() - timedelta(hours=3)
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.5

    def test_just_under_6_hours_returns_1_5(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = timezone.now() - timedelta(hours=5, minutes=59)
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.5

    def test_between_6_and_24_hours_returns_1_25(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = timezone.now() - timedelta(hours=12)
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.25

    def test_between_24_and_72_hours_returns_1_1(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = timezone.now() - timedelta(hours=48)
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.1

    def test_over_72_hours_returns_1_0(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = timezone.now() - timedelta(hours=100)
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.0

    def test_no_posted_at_returns_1_0(self, analyst, fresh_bounty):
        fresh_bounty.posted_at = None
        assert analyst._calculate_freshness_bonus(fresh_bounty) == 1.0

    def test_freshness_bonus_applied_in_roi(self, analyst, fresh_bounty):
        """Fresh bounty should score higher ROI than a stale one."""
        now = timezone.now()

        # Patch out AI and GitHub calls
        with patch.object(analyst, "_analyze_with_ai", return_value={
            "difficulty_score": 30,
            "estimated_hours": 4,
            "summary": "test",
            "approach": "",
            "has_clear_requirements": True,
            "has_tests": False,
            "has_ci": False,
            "has_contribution_guide": False,
            "required_skills": [],
            "risks": [],
        }), patch.object(analyst, "_assess_repo_quality", return_value=70):

            # Fresh bounty (2h old)
            fresh_bounty.posted_at = now - timedelta(hours=2)
            fresh_eval = analyst.evaluate(fresh_bounty)

            # Stale bounty (1 week old) — need a new bounty object
            from bounty_hunter.models.models import Bounty, Platform, BountyStatus
            stale = Bounty.objects.create(
                external_id="stale-001",
                platform=Platform.GITHUB,
                source_url="https://github.com/org/repo/issues/2",
                title="Fix auth bug",
                description="The auth module fails to handle unicode passwords correctly.",
                repo_owner="org",
                repo_name="repo",
                bounty_amount_usd=Decimal("200.00"),
                status=BountyStatus.DISCOVERED,
                posted_at=now - timedelta(days=7),
            )
            stale_eval = analyst.evaluate(stale)

        assert fresh_eval.roi_score > stale_eval.roi_score
