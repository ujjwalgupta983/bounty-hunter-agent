"""Tests for the multi-provider AI client."""
import json
import pytest
from unittest.mock import patch, MagicMock


def test_parse_json_valid():
    from bounty_hunter.utils.ai_client import _parse_json
    raw = '{"difficulty": 5, "estimated_hours": 3, "reasoning": "easy"}'
    result = _parse_json(raw)
    assert result["difficulty"] == 5
    assert result["estimated_hours"] == 3


def test_parse_json_with_markdown_fences():
    from bounty_hunter.utils.ai_client import _parse_json
    raw = '```json\n{"difficulty": 7, "estimated_hours": 8, "reasoning": "moderate"}\n```'
    result = _parse_json(raw)
    assert result["difficulty"] == 7


def test_parse_json_sets_default_keys():
    from bounty_hunter.utils.ai_client import _parse_json
    # Minimal JSON — should have all required keys set to defaults
    raw = '{"summary": "A fix", "estimated_hours": 2.0}'
    result = _parse_json(raw)
    assert "summary" in result
    assert "approach" in result
    assert "difficulty_score" in result
    assert result["difficulty_score"] == 50  # default
    assert result["has_tests"] is False       # default


def test_parse_json_invalid_raises():
    from bounty_hunter.utils.ai_client import _parse_json
    with pytest.raises(json.JSONDecodeError):
        _parse_json("this is not json")


def test_analyze_bounty_falls_back_on_exception():
    from bounty_hunter.utils.ai_client import analyze_bounty
    with patch("bounty_hunter.utils.ai_client._call_anthropic", side_effect=Exception("API error")):
        result = analyze_bounty("test prompt", {"AI_PROVIDER": "anthropic"})
    # Should return the fallback dict (not raise)
    assert "difficulty_score" in result
    assert "summary" in result
    assert "AI analysis unavailable" in result["summary"]


def test_analyze_bounty_returns_parsed_result():
    from bounty_hunter.utils.ai_client import analyze_bounty
    fake_response = '{"difficulty_score": 4, "estimated_hours": 5, "summary": "ok"}'
    with patch("bounty_hunter.utils.ai_client._call_anthropic", return_value=fake_response):
        result = analyze_bounty("test prompt", {"AI_PROVIDER": "anthropic"})
    assert result["difficulty_score"] == 4
    assert result["estimated_hours"] == 5
