"""
Tests for PaymentMethod model, Bounty payment fields, and Opire payment logic.

Covers:
  - PaymentMethod choices are importable and have correct values
  - Bounty model accepts payment_method and india_payable fields
  - india_payable defaults to False; True only for bank_transfer and crypto
  - OpireScout._extract_amount handles pendingPrice (cents) API format
  - OpireScout._process_bounty sets correct payment_method / india_payable
  - OpireScout._process_bounty parses repo info from project.url
"""
import pytest
from decimal import Decimal

from bounty_hunter.models.models import Bounty, Platform, PaymentMethod


# ---------------------------------------------------------------------------
# PaymentMethod choices
# ---------------------------------------------------------------------------

class TestPaymentMethodChoices:
    def test_all_choices_exist(self):
        assert PaymentMethod.STRIPE == "stripe"
        assert PaymentMethod.BANK_TRANSFER == "bank_transfer"
        assert PaymentMethod.CRYPTO == "crypto"
        assert PaymentMethod.PAYPAL == "paypal"
        assert PaymentMethod.UNKNOWN == "unknown"

    def test_choices_list_length(self):
        assert len(PaymentMethod.choices) == 5

    def test_choices_labels(self):
        labels = dict(PaymentMethod.choices)
        assert labels["stripe"] == "Stripe"
        assert labels["bank_transfer"] == "Bank Transfer"
        assert labels["crypto"] == "Crypto"
        assert labels["paypal"] == "PayPal"
        assert labels["unknown"] == "Unknown"


# ---------------------------------------------------------------------------
# Bounty model payment fields
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBountyPaymentFields:
    def _make_bounty(self, **kwargs):
        defaults = dict(
            external_id="pm-test-001",
            platform=Platform.OPIRE,
            source_url="https://opire.dev",
            title="Test bounty",
            description="Test",
            repo_owner="org",
            repo_name="repo",
            repo_url="https://github.com/org/repo",
            bounty_amount_usd=Decimal("100.00"),
        )
        defaults.update(kwargs)
        return Bounty.objects.create(**defaults)

    def test_default_payment_method_is_unknown(self):
        bounty = self._make_bounty()
        assert bounty.payment_method == PaymentMethod.UNKNOWN

    def test_default_india_payable_is_false(self):
        bounty = self._make_bounty()
        assert bounty.india_payable is False

    def test_stripe_payment_method(self):
        bounty = self._make_bounty(
            external_id="pm-test-002",
            payment_method=PaymentMethod.STRIPE,
            india_payable=False,
        )
        assert bounty.payment_method == "stripe"
        assert bounty.india_payable is False

    def test_crypto_payment_method_india_payable(self):
        bounty = self._make_bounty(
            external_id="pm-test-003",
            payment_method=PaymentMethod.CRYPTO,
            india_payable=True,
        )
        assert bounty.payment_method == "crypto"
        assert bounty.india_payable is True

    def test_bank_transfer_india_payable(self):
        bounty = self._make_bounty(
            external_id="pm-test-004",
            payment_method=PaymentMethod.BANK_TRANSFER,
            india_payable=True,
        )
        assert bounty.payment_method == "bank_transfer"
        assert bounty.india_payable is True

    def test_paypal_not_india_payable(self):
        bounty = self._make_bounty(
            external_id="pm-test-005",
            payment_method=PaymentMethod.PAYPAL,
            india_payable=False,
        )
        assert bounty.payment_method == "paypal"
        assert bounty.india_payable is False

    def test_payment_fields_persist_to_db(self):
        self._make_bounty(
            external_id="pm-test-006",
            payment_method=PaymentMethod.CRYPTO,
            india_payable=True,
        )
        b = Bounty.objects.get(external_id="pm-test-006")
        assert b.payment_method == "crypto"
        assert b.india_payable is True


# ---------------------------------------------------------------------------
# OpireScout._extract_amount — pendingPrice (cents) API format
# ---------------------------------------------------------------------------

@pytest.fixture
def opire_scout(db):
    from bounty_hunter.scouts.opire_scout import OpireScout
    return OpireScout()


class TestOpireExtractAmount:
    def test_pending_price_usd_cent(self, opire_scout):
        data = {"pendingPrice": {"value": 15000, "unit": "USD_CENT"}}
        assert opire_scout._extract_amount(data) == 150.0

    def test_pending_price_usd_cent_fractional(self, opire_scout):
        """$13.38 stored as 1338 cents."""
        data = {"pendingPrice": {"value": 1338, "unit": "USD_CENT"}}
        assert opire_scout._extract_amount(data) == pytest.approx(13.38)

    def test_pending_price_no_cent_unit_returns_as_is(self, opire_scout):
        """If unit is not a cents unit, value is returned as-is (already USD)."""
        data = {"pendingPrice": {"value": 200, "unit": "USD"}}
        assert opire_scout._extract_amount(data) == 200.0

    def test_flat_amount_key_fallback(self, opire_scout):
        data = {"amount": 75.0}
        assert opire_scout._extract_amount(data) == 75.0

    def test_flat_reward_key_fallback(self, opire_scout):
        data = {"reward": "250"}
        assert opire_scout._extract_amount(data) == 250.0

    def test_no_amount_returns_none(self, opire_scout):
        assert opire_scout._extract_amount({}) is None

    def test_pending_price_missing_value_falls_through(self, opire_scout):
        """pendingPrice dict with no 'value' key falls through to flat keys."""
        data = {"pendingPrice": {"unit": "USD_CENT"}, "amount": 50}
        assert opire_scout._extract_amount(data) == 50.0


# ---------------------------------------------------------------------------
# OpireScout._process_bounty — payment_method + india_payable
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOpireProcessBountyPayment:
    def test_default_stripe_payment_method(self, opire_scout):
        """Opire default payment is Stripe — india_payable should be False."""
        data = {
            "id": "opire-pay-001",
            "title": "Fix login bug",
            "description": "Login fails on Safari browsers.",
            "amount": 100,
            "url": "https://github.com/org/repo/issues/1",
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-pay-001")
        assert bounty.payment_method == PaymentMethod.STRIPE
        assert bounty.india_payable is False

    def test_crypto_keyword_sets_india_payable(self, opire_scout):
        """'crypto' in description → PaymentMethod.CRYPTO + india_payable=True."""
        data = {
            "id": "opire-pay-002",
            "title": "Integrate USDC payments",
            "description": "Add crypto payment support via USDC on Ethereum.",
            "amount": 500,
            "url": "https://github.com/org/repo/issues/2",
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-pay-002")
        assert bounty.payment_method == PaymentMethod.CRYPTO
        assert bounty.india_payable is True

    def test_bank_transfer_keyword_sets_india_payable(self, opire_scout):
        data = {
            "id": "opire-pay-003",
            "title": "Add bank transfer option",
            "description": "Support bank transfer and wire payments.",
            "amount": 300,
            "url": "https://github.com/org/repo/issues/3",
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-pay-003")
        assert bounty.payment_method == PaymentMethod.BANK_TRANSFER
        assert bounty.india_payable is True

    def test_paypal_keyword_not_india_payable(self, opire_scout):
        data = {
            "id": "opire-pay-004",
            "title": "Add PayPal checkout",
            "description": "Integrate paypal as payment option.",
            "amount": 200,
            "url": "https://github.com/org/repo/issues/4",
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-pay-004")
        assert bounty.payment_method == PaymentMethod.PAYPAL
        assert bounty.india_payable is False


# ---------------------------------------------------------------------------
# OpireScout._process_bounty — repo info from project.url
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOpireProcessBountyRepoInfo:
    def test_repo_parsed_from_project_url(self, opire_scout):
        """Opire API returns repo info in project.url, not top-level fields."""
        data = {
            "id": "opire-repo-001",
            "title": "Fix memory leak",
            "description": "Memory leak in worker process.",
            "pendingPrice": {"value": 20000, "unit": "USD_CENT"},  # $200
            "url": "https://github.com/myorg/myrepo/issues/55",
            "project": {"url": "https://github.com/myorg/myrepo"},
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-repo-001")
        assert bounty.repo_owner == "myorg"
        assert bounty.repo_name == "myrepo"
        assert bounty.issue_number == 55
        assert bounty.bounty_amount_usd == Decimal("200.00")

    def test_repo_parsed_from_issue_url_when_no_project(self, opire_scout):
        """Falls back to parsing repo from issue URL when project.url absent."""
        data = {
            "id": "opire-repo-002",
            "title": "Add dark mode",
            "description": "Implement dark mode toggle in settings.",
            "amount": 150,
            "url": "https://github.com/anotherorg/coolrepo/issues/99",
        }
        opire_scout._process_bounty(data)
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-repo-002")
        assert bounty.repo_owner == "anotherorg"
        assert bounty.repo_name == "coolrepo"
        assert bounty.issue_number == 99

    def test_real_api_format_end_to_end(self, opire_scout):
        """Full Opire API item shape — pendingPrice cents + project.url."""
        data = {
            "id": "opire-e2e-001",
            "title": "Refactor database layer",
            "description": "Extract DB logic into repository pattern.",
            "pendingPrice": {"value": 133800, "unit": "USD_CENT"},  # $1338
            "url": "https://github.com/realorg/realrepo/issues/7",
            "project": {"url": "https://github.com/realorg/realrepo"},
            "issue": {"title": "Refactor database layer"},
        }
        result = opire_scout._process_bounty(data)
        assert result == "new"
        bounty = Bounty.objects.get(platform=Platform.OPIRE, external_id="opire-e2e-001")
        assert bounty.bounty_amount_usd == Decimal("1338.00")
        assert bounty.repo_owner == "realorg"
        assert bounty.repo_name == "realrepo"
        assert bounty.issue_number == 7
