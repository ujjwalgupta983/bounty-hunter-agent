"""Tests for management commands."""
import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_bounty_report_runs():
    out = StringIO()
    call_command("bounty_report", "--days", "30", stdout=out)
    assert "Bounty Hunter Report" in out.getvalue() or "Scraped" in out.getvalue()


@pytest.mark.django_db
def test_bounty_report_json():
    out = StringIO()
    call_command("bounty_report", "--json", stdout=out)
    data = json.loads(out.getvalue())
    assert "bounties" in data
    assert "submissions" in data
    assert "earnings" in data
    assert "by_platform" in data


@pytest.mark.django_db
def test_bounty_report_all_time():
    out = StringIO()
    call_command("bounty_report", "--days", "0", "--json", stdout=out)
    data = json.loads(out.getvalue())
    assert data["days"] == 0


@pytest.mark.django_db
def test_list_bounties_empty():
    out = StringIO()
    call_command("list_bounties", stdout=out)
    # Should not crash with empty DB
    assert out.getvalue() is not None


@pytest.mark.django_db
def test_list_bounties_with_filter():
    out = StringIO()
    call_command("list_bounties", "--platform", "github", "--limit", "5", stdout=out)
    assert out.getvalue() is not None


@pytest.mark.django_db
def test_cleanup_dry_run():
    out = StringIO()
    call_command("cleanup", "--dry-run", stdout=out)
    output = out.getvalue()
    assert "dry" in output.lower() or "would" in output.lower() or "0" in output


@pytest.mark.django_db
def test_cleanup_default():
    out = StringIO()
    call_command("cleanup", "--older-than", "90", stdout=out)
    assert out.getvalue() is not None


@pytest.mark.django_db
def test_evaluate_bounty_not_found():
    from django.core.management.base import CommandError
    with pytest.raises(CommandError, match="does not exist"):
        call_command("evaluate_bounty", "99999")


@pytest.mark.django_db
def test_evaluate_bounty_all_empty():
    out = StringIO()
    call_command("evaluate_bounty", "--all", stdout=out)
    # No bounties — should warn and exit cleanly
    assert out.getvalue() is not None


@pytest.mark.django_db
def test_pick_targets_empty():
    out = StringIO()
    call_command("pick_targets", stdout=out)
    assert out.getvalue() is not None
