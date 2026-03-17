"""
Provider-agnostic AI client for bounty analysis.

Supports: anthropic | openai | openrouter

OpenRouter gives access to 100+ models (Claude, GPT-4o, Gemini, Llama, etc.)
via a single OpenAI-compatible API. Use model="openrouter/auto" to let
OpenRouter pick the best available model automatically.

Config (config/.env):
    ANALYST_AI_PROVIDER=openrouter        # anthropic | openai | openrouter
    ANALYST_AI_MODEL=openrouter/auto      # any model slug, or "openrouter/auto"
    OPENROUTER_API_KEY=sk-or-xxxxx
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# Fallback response when all providers fail
_FALLBACK = {
    "summary": "AI analysis unavailable",
    "approach": "",
    "estimated_hours": 4.0,
    "difficulty_score": 50,
    "has_clear_requirements": True,
    "has_tests": False,
    "has_ci": False,
    "has_contribution_guide": False,
    "required_skills": [],
    "risks": ["AI analysis failed — manual review recommended"],
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def analyze_bounty(prompt: str, config: dict) -> dict:
    """
    Send prompt to the configured AI provider and return parsed JSON dict.

    Falls back to _FALLBACK if the call fails or JSON can't be parsed.
    """
    provider = config.get("AI_PROVIDER", "anthropic").lower()

    try:
        if provider == "anthropic":
            raw = _call_anthropic(prompt, config)
        elif provider == "openrouter":
            raw = _call_openrouter(prompt, config)
        elif provider == "openai":
            raw = _call_openai(prompt, config)
        else:
            logger.warning("ai_client: unknown provider '%s', falling back to anthropic", provider)
            raw = _call_anthropic(prompt, config)

        return _parse_json(raw)

    except Exception as exc:
        logger.warning("ai_client: analysis failed (%s %s): %s", provider, config.get("AI_MODEL", ""), exc)
        return _FALLBACK.copy()


# ── Provider implementations ──────────────────────────────────────────────────

def _call_anthropic(prompt: str, config: dict) -> str:
    import anthropic

    api_key = config.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    model = config.get("AI_MODEL") or "claude-sonnet-4-20250514"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_openrouter(prompt: str, config: dict) -> str:
    from openai import OpenAI

    api_key = config.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    # "openrouter/auto" → OpenRouter picks the best model automatically
    model = config.get("AI_MODEL") or "openrouter/auto"

    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/ujjwalgupta983/bounty-hunter-agent",
            "X-Title": "Bounty Hunter Agent",
        },
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _call_openai(prompt: str, config: dict) -> str:
    from openai import OpenAI

    api_key = config.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    model = config.get("AI_MODEL") or "gpt-4o-mini"

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extract and parse JSON from model response (handles markdown fences)."""
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1)

    result = json.loads(text.strip())

    # Validate required keys exist with sensible types
    result.setdefault("summary", "")
    result.setdefault("approach", "")
    result.setdefault("estimated_hours", 4.0)
    result.setdefault("difficulty_score", 50)
    result.setdefault("has_clear_requirements", True)
    result.setdefault("has_tests", False)
    result.setdefault("has_ci", False)
    result.setdefault("has_contribution_guide", False)
    result.setdefault("required_skills", [])
    result.setdefault("risks", [])

    return result
