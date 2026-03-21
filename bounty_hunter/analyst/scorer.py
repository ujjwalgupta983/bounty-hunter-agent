"""
Bounty Analyst — Evaluates and scores bounties for ROI.

Uses AI to estimate difficulty, then calculates ROI based on
payout, difficulty, competition, tech stack match, and repo quality.
"""
import logging
from decimal import Decimal

import httpx
from django.conf import settings

from bounty_hunter.models.models import Bounty, Evaluation, Difficulty, BountyStatus

logger = logging.getLogger(__name__)

# Languages/frameworks we're strong in (ordered by proficiency)
STRONG_LANGUAGES = {
    "Python": 95,
    "JavaScript": 90,
    "TypeScript": 90,
    "Go": 80,
    "Rust": 75,
    "Java": 70,
    "Ruby": 65,
    "C++": 60,
    "Solidity": 70,
    "PHP": 60,
    "Swift": 50,
    "Kotlin": 55,
}

DEFAULT_TECH_MATCH = 50  # For unknown languages


class BountyAnalyst:
    """Evaluates bounties and assigns ROI scores."""

    def __init__(self):
        self.config = settings.BOUNTY_HUNTER
        self.min_roi = self.config["MIN_ROI_SCORE"]

    def evaluate(self, bounty: Bounty) -> Evaluation | None:
        """Evaluate a single bounty. Returns the Evaluation or None if auto-rejected."""

        # Skip if already evaluated
        if hasattr(bounty, "evaluation"):
            return bounty.evaluation

        # Auto-rejection checks
        rejection_reason = self._check_auto_reject(bounty)
        if rejection_reason:
            eval_obj = Evaluation.objects.create(
                bounty=bounty,
                roi_score=0,
                difficulty_score=0,
                tech_match_score=0,
                competition_score=0,
                repo_quality_score=0,
                estimated_hours=0,
                estimated_difficulty=Difficulty.MEDIUM,
                effective_hourly_rate=0,
                analysis_summary=f"Auto-rejected: {rejection_reason}",
                auto_rejected=True,
                rejection_reason=rejection_reason,
            )
            bounty.status = BountyStatus.EVALUATED
            bounty.save()
            logger.info(f"Auto-rejected: {bounty.title[:60]} — {rejection_reason}")
            return eval_obj

        # AI-powered analysis
        analysis = self._analyze_with_ai(bounty)

        # Calculate scores
        tech_match = self._calculate_tech_match(bounty)
        competition = self._calculate_competition_score(bounty)
        repo_quality = self._assess_repo_quality(bounty)
        difficulty = analysis.get("difficulty_score", 50)
        estimated_hours = analysis.get("estimated_hours", 4)

        # Calculate ROI
        hourly_rate = float(bounty.bounty_amount_usd) / max(estimated_hours, 0.5)
        competition_factor = competition / 100
        tech_factor = tech_match / 100

        roi_score = min(100, (
            (float(bounty.bounty_amount_usd) / max(estimated_hours, 0.5)) *  # Base $/hr
            tech_factor *  # Tech match multiplier
            competition_factor *  # Competition multiplier
            (repo_quality / 100) *  # Quality multiplier
            ((100 - difficulty) / 100)  # Inverse difficulty
        ) / 2)  # Normalize to 0-100 range

        # Map difficulty score to enum
        if difficulty < 20:
            diff_enum = Difficulty.TRIVIAL
        elif difficulty < 40:
            diff_enum = Difficulty.EASY
        elif difficulty < 60:
            diff_enum = Difficulty.MEDIUM
        elif difficulty < 80:
            diff_enum = Difficulty.HARD
        else:
            diff_enum = Difficulty.EXPERT

        eval_obj = Evaluation.objects.create(
            bounty=bounty,
            roi_score=round(roi_score, 2),
            difficulty_score=difficulty,
            tech_match_score=tech_match,
            competition_score=competition,
            repo_quality_score=repo_quality,
            estimated_hours=estimated_hours,
            estimated_difficulty=diff_enum,
            effective_hourly_rate=Decimal(str(round(hourly_rate, 2))),
            analysis_summary=analysis.get("summary", ""),
            approach_suggestion=analysis.get("approach", ""),
            risks=analysis.get("risks", []),
            required_skills=analysis.get("required_skills", []),
            has_clear_requirements=analysis.get("has_clear_requirements", True),
            has_tests=analysis.get("has_tests", False),
            has_ci=analysis.get("has_ci", False),
            has_contribution_guide=analysis.get("has_contribution_guide", False),
        )

        if analysis.get("summary") == "AI analysis unavailable":
            eval_obj.needs_reeval = True
            eval_obj.save()

        bounty.status = BountyStatus.EVALUATED
        bounty.save()

        logger.info(
            f"Evaluated: ${bounty.bounty_amount_usd} — ROI: {roi_score:.1f} — "
            f"{bounty.title[:60]}"
        )

        return eval_obj

    def _check_auto_reject(self, bounty: Bounty) -> str | None:
        """Check if bounty should be auto-rejected. Returns reason or None."""
        if bounty.bounty_amount_usd < self.config["MIN_BOUNTY_USD"]:
            return f"Below minimum bounty (${self.config['MIN_BOUNTY_USD']})"

        if bounty.existing_prs > 5:
            return f"Too many existing PRs ({bounty.existing_prs})"

        if bounty.competitors_count > 10:
            return f"Too much competition ({bounty.competitors_count} competitors)"

        # Check if description is too vague
        if len(bounty.description) < 50 and not bounty.title:
            return "Insufficient description"

        return None

    def _calculate_tech_match(self, bounty: Bounty) -> float:
        """Calculate how well our tech stack matches. Returns 0-100."""
        language = bounty.language.strip()
        if language and language in STRONG_LANGUAGES:
            return STRONG_LANGUAGES[language]

        # Check labels for language hints
        for label in bounty.labels:
            label_lower = label.lower().strip()
            for lang, score in STRONG_LANGUAGES.items():
                if lang.lower() in label_lower:
                    return score

        return DEFAULT_TECH_MATCH

    def _calculate_competition_score(self, bounty: Bounty) -> float:
        """Calculate competition factor. Higher = less competition = better. Returns 0-100."""
        competitors = bounty.competitors_count + bounty.existing_prs

        if competitors == 0:
            return 100
        elif competitors <= 2:
            return 80
        elif competitors <= 5:
            return 60
        elif competitors <= 10:
            return 40
        else:
            return 20

    def _assess_repo_quality(self, bounty: Bounty) -> float:
        """Assess repo quality via GitHub API. Returns 0-100."""
        try:
            token = self.config["GITHUB_TOKEN"]
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }

            with httpx.Client(headers=headers, timeout=15) as client:
                response = client.get(
                    f"https://api.github.com/repos/{bounty.repo_owner}/{bounty.repo_name}"
                )

                if response.status_code != 200:
                    return 50  # Default if we can't check

                repo = response.json()

            score = 50  # Base score

            # Stars indicate project maturity
            stars = repo.get("stargazers_count", 0)
            if stars > 1000:
                score += 15
            elif stars > 100:
                score += 10
            elif stars > 10:
                score += 5

            # Has description
            if repo.get("description"):
                score += 5

            # Has license
            if repo.get("license"):
                score += 10

            # Not archived
            if repo.get("archived"):
                score -= 30

            # Recent activity
            if repo.get("pushed_at"):
                from datetime import datetime, timedelta
                from django.utils import timezone
                pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
                days_since = (timezone.now() - pushed).days
                if days_since < 7:
                    score += 15
                elif days_since < 30:
                    score += 10
                elif days_since > 180:
                    score -= 10

            return min(100, max(0, score))

        except Exception as e:
            logger.warning(f"Failed to assess repo quality: {e}")
            return 50

    def _build_prompt(self, bounty: Bounty) -> str:
        return f"""Analyze this GitHub bounty issue and provide an assessment.

Title: {bounty.title}
Repository: {bounty.repo_owner}/{bounty.repo_name}
Language: {bounty.language or 'Unknown'}
Labels: {', '.join(bounty.labels)}
Bounty Amount: ${bounty.bounty_amount_usd}

Issue Description:
{bounty.description[:3000]}

Respond in JSON format:
{{
    "summary": "Brief analysis of what needs to be done",
    "approach": "Suggested technical approach",
    "estimated_hours": <float, estimated hours to complete>,
    "difficulty_score": <int 0-100, where 0=trivial 100=expert>,
    "has_clear_requirements": <bool>,
    "has_tests": <bool, if mentioned or likely>,
    "has_ci": <bool, if mentioned or likely>,
    "has_contribution_guide": <bool, if mentioned or likely>,
    "required_skills": ["skill1", "skill2"],
    "risks": ["risk1", "risk2"]
}}"""

    def _call_anthropic(self, bounty: Bounty) -> dict:
        import anthropic
        from bounty_hunter.utils.ai_client import _parse_json

        api_key = self.config.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        model = self.config.get("AI_MODEL") or "claude-sonnet-4-20250514"
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": self._build_prompt(bounty)}],
        )
        return _parse_json(response.content[0].text)

    def _call_openai(self, bounty: Bounty) -> dict:
        from openai import OpenAI
        from bounty_hunter.utils.ai_client import _parse_json

        api_key = self.config.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            messages=[{"role": "user", "content": self._build_prompt(bounty)}],
        )
        return _parse_json(response.choices[0].message.content)

    def _analyze_with_ai(self, bounty: Bounty) -> dict:
        """Try Anthropic, then OpenAI. Returns defaults dict on total failure."""
        logger.info(
            "analyst: calling AI for bounty %d (Anthropic first)", bounty.id
        )

        try:
            return self._call_anthropic(bounty)
        except Exception as exc:
            err_str = str(exc).lower()
            logger.warning("analyst: Anthropic failed for bounty %d: %s", bounty.id, exc)
            if "credit balance" in err_str or "billing" in err_str:
                try:
                    from bounty_hunter.utils.notifications import notifier
                    notifier.send("🚨 AI Credits Exhausted")
                except Exception:
                    pass

        try:
            logger.info("analyst: trying OpenAI fallback for bounty %d", bounty.id)
            return self._call_openai(bounty)
        except Exception as exc:
            logger.warning("analyst: OpenAI fallback failed for bounty %d: %s", bounty.id, exc)

        return {
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
