"""Tests for bounty scouts."""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from bounty_hunter.scouts.github_scout import GitHubScout
from bounty_hunter.scouts.opire_scout import OpireScout
from bounty_hunter.scouts.issuehunt_scout import IssueHuntScout
from bounty_hunter.models.models import Platform


# ---------------------------------------------------------------------------
# GitHubScout helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def github_scout(db):
    return GitHubScout()


class TestGitHubScoutExtractAmount:
    def test_dollar_sign_in_title(self, github_scout):
        assert github_scout._extract_amount("Fix auth bug [BOUNTY $500]", "", []) == 500.0

    def test_usd_suffix(self, github_scout):
        assert github_scout._extract_amount("", "reward: 250 USD", []) == 250.0

    def test_bounty_keyword(self, github_scout):
        assert github_scout._extract_amount("", "bounty: $1000", []) == 1000.0

    def test_comma_separated_amount(self, github_scout):
        amount = github_scout._extract_amount("$1,500 bounty available", "", [])
        assert amount == 1500.0

    def test_no_amount_returns_none(self, github_scout):
        assert github_scout._extract_amount("Fix a bug", "Some description", []) is None

    def test_amount_from_labels(self, github_scout):
        amount = github_scout._extract_amount("", "", ["bounty $200"])
        assert amount == 200.0

    def test_amount_sanity_check_too_large(self, github_scout):
        # 2 million is above the 1_000_000 sanity cap
        assert github_scout._extract_amount("$2,000,000 reward", "", []) is None


class TestGitHubScoutNoiseFilter:
    def test_proposal_title_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 1,
            "title": "Governance proposal: increase reward pool",
            "body": "This proposal would increase the reward budget by $500 for contributors.",
            "labels": [{"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_airdrop_title_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 2,
            "title": "Airdrop $500 to early contributors",
            "body": "We will airdrop tokens worth $500 to qualifying addresses.",
            "labels": [{"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_paper_note_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 3,
            "title": "Paper note on reward system design $100",
            "body": "This paper note outlines a $100 reward distribution strategy.",
            "labels": [{"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_governance_label_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 4,
            "title": "Increase bug bounty reward $200",
            "body": "Let's increase the bug bounty reward to $200 for all contributors.",
            "labels": [{"name": "governance"}, {"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_proposal_label_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 5,
            "title": "Contributor reward program $300",
            "body": "Bug fix proposal for the auth module worth $300.",
            "labels": [{"name": "proposal"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_rip_pattern_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 6,
            "title": "RIP-42: token reward distribution $500",
            "body": "This RIP proposes a new token reward distribution mechanism worth $500.",
            "labels": [{"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"

    def test_no_code_signals_skipped(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 7,
            "title": "Design new logo $500",
            "body": "We are looking for a new logo design, reward $500 USD.",
            "labels": [{"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
        }
        assert github_scout._process_issue(issue) == "skipped"


@pytest.mark.django_db
class TestGitHubScoutRealBountyPassThrough:
    def test_real_bug_bounty_passes(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 10,
            "title": "Fix crash in API endpoint [BOUNTY $500]",
            "body": "There is a bug causing a crash in the /api/users endpoint. Implement a fix and add tests.",
            "labels": [{"name": "bug"}, {"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
            "html_url": "https://github.com/org/repo/issues/10",
            "comments": 0,
        }
        result = github_scout._process_issue(issue)
        assert result in ("new", "updated")

    def test_feature_bounty_passes(self, github_scout):
        issue = {
            "repository_url": "https://api.github.com/repos/org/repo",
            "number": 11,
            "title": "Implement CSV export feature [BOUNTY $200]",
            "body": "We need to implement CSV export. The function should call the api endpoint and refactor the class.",
            "labels": [{"name": "feature"}, {"name": "bounty"}],
            "created_at": "2026-01-01T00:00:00Z",
            "html_url": "https://github.com/org/repo/issues/11",
            "comments": 1,
        }
        result = github_scout._process_issue(issue)
        assert result in ("new", "updated")


class TestHasCodeSignals:
    def test_two_signals_returns_true(self, github_scout):
        assert github_scout._has_code_signals("fix bug in auth", "", []) is True

    def test_one_signal_returns_false(self, github_scout):
        assert github_scout._has_code_signals("fix the problem", "no technical content here", []) is False

    def test_signals_from_body(self, github_scout):
        assert github_scout._has_code_signals("", "implement a new feature with tests", []) is True

    def test_signals_from_labels(self, github_scout):
        assert github_scout._has_code_signals("bounty", "", ["bug", "fix"]) is True

    def test_no_signals_returns_false(self, github_scout):
        assert github_scout._has_code_signals("logo design reward", "we want a new design", []) is False


class TestGitHubScoutDetectLanguage:
    def test_python_label(self, github_scout):
        assert github_scout._detect_language(["python", "bug"]) == "Python"

    def test_typescript_label(self, github_scout):
        assert github_scout._detect_language(["typescript"]) == "TypeScript"

    def test_golang_maps_to_go(self, github_scout):
        assert github_scout._detect_language(["golang", "performance"]) == "Go"

    def test_rust_label(self, github_scout):
        assert github_scout._detect_language(["rust"]) == "Rust"

    def test_no_language_label(self, github_scout):
        assert github_scout._detect_language(["bug", "enhancement"]) == ""

    def test_empty_labels(self, github_scout):
        assert github_scout._detect_language([]) == ""


# ---------------------------------------------------------------------------
# OpireScout helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def opire_scout(db):
    return OpireScout()


@pytest.mark.django_db
class TestOpireScoutProcessBounty:
    def test_valid_item_creates_bounty(self, opire_scout):
        data = {
            "id": "opire-001",
            "title": "Fix broken auth flow",
            "description": "Detailed description of the auth issue to be fixed by someone.",
            "amount": 150,
            "repo_owner": "testorg",
            "repo_name": "testrepo",
            "issue_number": 42,
            "url": "https://github.com/testorg/testrepo/issues/42",
        }
        result = opire_scout._process_bounty(data)
        assert result == "new"

    def test_below_minimum_skipped(self, opire_scout):
        data = {
            "id": "opire-002",
            "title": "Cheap bounty",
            "amount": 10,  # Below $50 minimum
            "repo_owner": "org",
            "repo_name": "repo",
            "url": "https://github.com/org/repo/issues/1",
        }
        result = opire_scout._process_bounty(data)
        assert result == "skipped"

    def test_no_github_url_still_creates(self, opire_scout):
        """Bounty without GitHub URL should still be created if amount is valid."""
        data = {
            "id": "opire-003",
            "title": "Fix something on Opire",
            "amount": 100,
            "repo_owner": "",
            "repo_name": "",
            "url": "",
        }
        result = opire_scout._process_bounty(data)
        assert result == "new"

    def test_duplicate_returns_updated(self, opire_scout):
        data = {
            "id": "opire-dup-001",
            "title": "Fix broken auth flow",
            "description": "Auth issue description",
            "amount": 100,
            "repo_owner": "testorg",
            "repo_name": "testrepo",
            "issue_number": 99,
            "url": "https://github.com/testorg/testrepo/issues/99",
        }
        opire_scout._process_bounty(data)
        result = opire_scout._process_bounty(data)  # second call should update
        assert result == "updated"


# ---------------------------------------------------------------------------
# IssueHuntScout helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def issuehunt_scout(db):
    return IssueHuntScout()


@pytest.mark.django_db
class TestIssueHuntScoutProcessBounty:
    def test_valid_item_creates_bounty(self, issuehunt_scout):
        data = {
            "id": "issuehunt-001",
            "title": "Implement dark mode",
            "description": "Users have requested dark mode support for the dashboard UI.",
            "amount": 200,
            "repo_owner": "uiorg",
            "repo_name": "dashboard",
            "issue_number": 77,
            "url": "https://github.com/uiorg/dashboard/issues/77",
        }
        result = issuehunt_scout._process_bounty(data)
        assert result == "new"

    def test_below_minimum_skipped(self, issuehunt_scout):
        data = {
            "id": "issuehunt-002",
            "title": "Cheap fix",
            "amount": 5,
            "url": "",
        }
        result = issuehunt_scout._process_bounty(data)
        assert result == "skipped"

    def test_fund_amount_field_accepted(self, issuehunt_scout):
        """IssueHunt uses fund_amount field."""
        data = {
            "id": "issuehunt-003",
            "title": "Performance optimization task",
            "description": "Profile and optimize the hot path in the data pipeline.",
            "fund_amount": 75.0,
            "repo_owner": "perforg",
            "repo_name": "pipeline",
            "issue_number": 5,
            "url": "https://github.com/perforg/pipeline/issues/5",
        }
        result = issuehunt_scout._process_bounty(data)
        assert result == "new"

    def test_api_response_format(self, issuehunt_scout):
        """API-style response with nested fields."""
        data = {
            "issueId": "issuehunt-api-001",
            "issueTitle": "Fix broken link",
            "issueBody": "Link on homepage is broken and needs fixing urgently.",
            "fundAmount": 60,
            "owner": "webteam",
            "repo": "site",
            "number": 12,
            "html_url": "https://github.com/webteam/site/issues/12",
        }
        result = issuehunt_scout._process_bounty(data)
        assert result == "new"


# ---------------------------------------------------------------------------
# scan() integration tests (mocked _fetch_bounties)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_opire_scan_with_mocked_fetch(opire_scout):
    mock_bounties = [
        {
            "id": "mock-opire-1",
            "title": "Fix websocket reconnection",
            "description": "Websocket drops and never reconnects after network blip.",
            "amount": 300,
            "repo_owner": "socketteam",
            "repo_name": "realtime",
            "issue_number": 33,
            "url": "https://github.com/socketteam/realtime/issues/33",
        }
    ]
    with patch.object(OpireScout, "_fetch_bounties", return_value=mock_bounties):
        stats = opire_scout.scan()
    assert stats["found"] == 1
    assert stats["new"] == 1
    assert stats["errors"] == []


@pytest.mark.django_db
def test_issuehunt_scan_with_mocked_fetch(issuehunt_scout):
    mock_bounties = [
        {
            "id": "mock-ih-1",
            "title": "Implement CSV export feature",
            "description": "Users need to export their data as CSV from the reports screen.",
            "amount": 150,
            "repo_owner": "dataapp",
            "repo_name": "core",
            "issue_number": 88,
            "url": "https://github.com/dataapp/core/issues/88",
        }
    ]
    with patch.object(IssueHuntScout, "_fetch_bounties", return_value=mock_bounties):
        stats = issuehunt_scout.scan()
    assert stats["found"] == 1
    assert stats["new"] == 1
    assert stats["errors"] == []


@pytest.mark.django_db
def test_opire_scan_empty_fetch(opire_scout):
    with patch.object(OpireScout, "_fetch_bounties", return_value=[]):
        stats = opire_scout.scan()
    assert stats["found"] == 0
    assert stats["new"] == 0


@pytest.mark.django_db
def test_issuehunt_scan_empty_fetch(issuehunt_scout):
    with patch.object(IssueHuntScout, "_fetch_bounties", return_value=[]):
        stats = issuehunt_scout.scan()
    assert stats["found"] == 0
    assert stats["new"] == 0
