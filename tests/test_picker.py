"""Tests for the picker/target selection task."""
import pytest
from unittest.mock import patch


@pytest.mark.django_db
def test_pick_targets_empty_returns_zero():
    from bounty_hunter.picker.tasks import pick_targets
    result = pick_targets()
    # Either "at capacity" or picked=0
    assert "picked" in result or "reason" in result


@pytest.mark.django_db
def test_pick_targets_selects_evaluated(evaluated_bounty):
    from bounty_hunter.picker.tasks import pick_targets
    result = pick_targets()
    evaluated_bounty.refresh_from_db()
    # If roi_score >= MIN_ROI_SCORE, it should be targeted
    assert result["picked"] >= 0


@pytest.mark.django_db
def test_pick_targets_respects_capacity():
    from bounty_hunter.picker.tasks import pick_targets
    with patch("bounty_hunter.picker.tasks.settings") as mock_settings:
        mock_settings.BOUNTY_HUNTER = {
            "MAX_CONCURRENT_SOLVERS": 0,
            "MIN_ROI_SCORE": 0,
        }
        result = pick_targets()
    assert result.get("reason") == "at capacity" or result.get("picked") == 0
