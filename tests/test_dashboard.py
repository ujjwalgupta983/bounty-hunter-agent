import pytest
from django.test import Client


@pytest.mark.django_db
def test_dashboard_loads():
    assert Client().get("/dashboard/").status_code == 200


@pytest.mark.django_db
def test_dashboard_root():
    assert Client().get("/").status_code == 200


@pytest.mark.django_db
def test_dashboard_has_title():
    resp = Client().get("/dashboard/")
    assert b"Bounty Hunter" in resp.content


@pytest.mark.django_db
def test_dashboard_returns_200():
    client = Client()
    response = client.get("/dashboard/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_dashboard_contains_stats(bounty):
    client = Client()
    response = client.get("/dashboard/")
    content = response.content.decode()
    assert "Total Bounties" in content


@pytest.mark.django_db
def test_dashboard_context_has_stats(bounty):
    client = Client()
    response = client.get("/dashboard/")
    assert "stats" in response.context
    assert "bounties" in response.context


@pytest.mark.django_db
def test_dashboard_stats_keys(bounty):
    client = Client()
    response = client.get("/dashboard/")
    stats = response.context["stats"]
    for key in ["total", "active", "submitted", "merged", "earned"]:
        assert key in stats
