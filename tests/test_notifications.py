"""Tests for Telegram notifications."""
import pytest
from unittest.mock import patch, MagicMock
from bounty_hunter.utils.notifications import TelegramNotifier


def make_notifier(token="", chat_id=""):
    n = TelegramNotifier.__new__(TelegramNotifier)
    n.token = token
    n.chat_id = chat_id
    return n


def test_send_no_config_returns_false():
    n = make_notifier()
    assert n.send("hello") is False


def test_send_success():
    n = make_notifier(token="tok", chat_id="123")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_resp
        assert n.send("hello") is True


def test_send_api_error_returns_false():
    n = make_notifier(token="tok", chat_id="123")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.post.return_value = mock_resp
        assert n.send("hello") is False


def test_send_network_error_returns_false():
    n = make_notifier(token="tok", chat_id="123")
    with patch("httpx.Client", side_effect=Exception("no network")):
        assert n.send("hello") is False


def test_notify_high_value_bounty():
    n = make_notifier()  # no token → False silently
    b = MagicMock()
    b.title = "Fix login bug"
    b.bounty_amount_usd = 500
    b.platform = "github"
    b.source_url = "https://github.com/test/repo/issues/1"
    assert n.notify_high_value_bounty(b) is False


def test_notify_targeted():
    n = make_notifier()
    b = MagicMock()
    b.title = "Add feature"
    b.bounty_amount_usd = 300
    b.platform = "algora"
    b.source_url = "https://github.com/test/repo/issues/2"
    e = MagicMock()
    e.roi_score = 72.5
    e.estimated_hours = 3.0
    assert n.notify_targeted(b, e) is False


def test_notify_pr_merged_with_earning():
    n = make_notifier()
    b = MagicMock()
    b.title = "Fix bug"
    b.bounty_amount_usd = 200
    b.platform = "github"
    s = MagicMock()
    s.pr_url = "https://github.com/test/repo/pull/5"
    earning = MagicMock()
    earning.net_earning_usd = 180
    assert n.notify_pr_merged(b, s, earning) is False


def test_daily_digest():
    n = make_notifier()
    stats = {"scraped": 50, "targeted": 5, "prs_open": 3, "confirmed_usd": 400.0, "pending_usd": 200.0}
    assert n.daily_digest(stats) is False


def test_singleton_import():
    from bounty_hunter.utils.notifications import notifier
    assert isinstance(notifier, TelegramNotifier)
