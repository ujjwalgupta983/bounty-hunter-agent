"""Shared pytest fixtures for the bounty hunter test suite."""
import pytest
from decimal import Decimal


@pytest.fixture
def bounty(db):
    from bounty_hunter.models.models import Bounty, Platform, BountyStatus
    return Bounty.objects.create(
        external_id="test-001",
        platform=Platform.GITHUB,
        source_url="https://github.com/testorg/testrepo/issues/1",
        title="Fix the authentication bug",
        description="The auth module fails to handle unicode passwords correctly.",
        repo_owner="testorg",
        repo_name="testrepo",
        repo_url="https://github.com/testorg/testrepo",
        issue_number=1,
        bounty_amount_usd=Decimal("200.00"),
        status=BountyStatus.DISCOVERED,
    )


@pytest.fixture
def evaluated_bounty(bounty):
    from bounty_hunter.models.models import Evaluation, BountyStatus
    Evaluation.objects.create(
        bounty=bounty,
        roi_score=75.0,
        difficulty_score=30.0,
        tech_match_score=80.0,
        competition_score=70.0,
        repo_quality_score=80.0,
        estimated_hours=4.0,
        estimated_difficulty="easy",
        effective_hourly_rate=Decimal("50.00"),
        analysis_summary="Straightforward auth fix with clear reproduction steps.",
        auto_rejected=False,
        rejection_reason="",
    )
    bounty.status = BountyStatus.EVALUATED
    bounty.save()
    return bounty
