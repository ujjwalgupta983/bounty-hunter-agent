import pytest


@pytest.mark.django_db
def test_check_all_prs_empty():
    from bounty_hunter.tracker.tasks import check_all_prs
    assert check_all_prs()["checked"] == 0


@pytest.mark.django_db
def test_ping_stale_empty():
    from bounty_hunter.tracker.tasks import ping_stale_prs
    assert ping_stale_prs()["stale"] == 0


@pytest.mark.django_db
def test_record_earning_missing():
    from bounty_hunter.tracker.tasks import record_earning
    record_earning(99999)  # should not raise
