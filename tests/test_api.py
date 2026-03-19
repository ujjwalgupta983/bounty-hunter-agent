"""Tests for REST API endpoints."""
import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestBountyAPI:
    def setup_method(self):
        self.client = Client()

    def test_bounty_list_empty(self):
        response = self.client.get("/api/v1/bounties/")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["count"] == 0

    def test_bounty_list_returns_bounty(self, bounty):
        response = self.client.get("/api/v1/bounties/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1

    def test_bounty_detail(self, bounty):
        response = self.client.get(f"/api/v1/bounties/{bounty.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == bounty.id
        assert "title" in data

    def test_dashboard_endpoint(self):
        response = self.client.get("/api/v1/dashboard/")
        assert response.status_code == 200
        data = response.json()
        # Dashboard returns nested structure: {"bounties": {"total": ...}, ...}
        assert "bounties" in data
        assert "total" in data["bounties"]

    def test_top_opportunities_endpoint(self):
        response = self.client.get("/api/v1/bounties/top_opportunities/")
        assert response.status_code == 200

    def test_active_bounties_endpoint(self):
        response = self.client.get("/api/v1/bounties/active/")
        assert response.status_code == 200
