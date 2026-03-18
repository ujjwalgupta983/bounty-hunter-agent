"""
Solver Agent — multi-stage pipeline to fix bounty issues autonomously.

Stages: EXPLORER → PLANNER → CODER → TESTER → REVIEWER → (ITERATE) → READY
"""
import logging
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class SolverAgent:

    def __init__(self):
        self.config = settings.BOUNTY_HUNTER

    def solve(self, bounty):
        """Orchestrate all stages. Returns Solution or None on failure."""
        from bounty_hunter.models.models import Solution, BountyStatus

        solution = Solution.objects.create(
            bounty=bounty,
            status=Solution.SolverStatus.EXPLORING,
            max_iterations=self.config.get("SOLVER_MAX_ITERATIONS", 3),
        )
        bounty.status = BountyStatus.IN_PROGRESS
        bounty.save(update_fields=["status", "updated_at"])

        start = time.time()
        try:
            # Stage 1: Explore
            repo_context = self._explore(bounty, solution)

            # Stage 2: Plan
            solution.status = Solution.SolverStatus.PLANNING
            solution.save(update_fields=["status"])
            plan = self._plan(bounty, solution, repo_context)
            solution.implementation_plan = plan
            solution.save(update_fields=["implementation_plan"])

            # Stage 3: Code
            solution.status = Solution.SolverStatus.CODING
            solution.save(update_fields=["status"])
            self._code(bounty, solution, plan)

            # Stage 4: Test
            solution.status = Solution.SolverStatus.TESTING
            solution.save(update_fields=["status"])
            self._test(solution)

            # Stage 5: Review + iterate
            for i in range(solution.max_iterations):
                solution.status = Solution.SolverStatus.REVIEWING
                solution.save(update_fields=["status"])
                approved, notes = self._review(bounty, solution)
                solution.review_notes = notes
                solution.iteration_count = i + 1
                if approved:
                    solution.review_approved = True
                    solution.status = Solution.SolverStatus.READY
                    solution.save(update_fields=["review_approved", "status", "review_notes", "iteration_count"])
                    break
                elif i < solution.max_iterations - 1:
                    solution.status = Solution.SolverStatus.ITERATING
                    solution.save(update_fields=["status", "review_notes", "iteration_count"])
                    self._code(bounty, solution, plan + f"\n\nReview feedback:\n{notes}")
                    self._test(solution)
                else:
                    logger.warning("solver: max iterations reached for bounty %d", bounty.id)
                    solution.status = Solution.SolverStatus.FAILED
                    solution.save(update_fields=["status", "review_notes", "iteration_count"])
                    return None

        except Exception as exc:
            logger.exception("solver: pipeline failed for bounty %d: %s", bounty.id, exc)
            solution.status = Solution.SolverStatus.FAILED
            solution.save(update_fields=["status"])
            return None
        finally:
            elapsed = int(time.time() - start)
            solution.time_spent_seconds = elapsed
            solution.completed_at = timezone.now()
            solution.save(update_fields=["time_spent_seconds", "completed_at"])

        logger.info("solver: bounty %d solved in %ds", bounty.id, int(time.time() - start))
        return solution

    def _explore(self, bounty, solution) -> str:
        """Fetch repo structure and key files via GitHub API."""
        import httpx
        token = self.config.get("GITHUB_TOKEN", "")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"} if token else {}
        context_parts = [f"Repository: {bounty.repo_full_name}", f"Issue #{bounty.issue_number}: {bounty.title}", "", bounty.description[:2000]]

        try:
            with httpx.Client(headers=headers, timeout=20) as client:
                # Get file tree
                resp = client.get(f"https://api.github.com/repos/{bounty.repo_full_name}/git/trees/HEAD?recursive=1")
                if resp.status_code == 200:
                    tree = resp.json().get("tree", [])
                    files = [f["path"] for f in tree if f.get("type") == "blob" and not f["path"].startswith(".")][:100]
                    context_parts.append(f"\nRepository files ({len(files)} shown):\n" + "\n".join(files[:50]))

                # Read key files
                for key_file in ["README.md", "CONTRIBUTING.md", "setup.py", "pyproject.toml", "package.json"]:
                    r = client.get(f"https://api.github.com/repos/{bounty.repo_full_name}/contents/{key_file}")
                    if r.status_code == 200:
                        import base64
                        content = base64.b64decode(r.json().get("content", "")).decode("utf-8", errors="ignore")[:1000]
                        context_parts.append(f"\n{key_file}:\n{content}")
                        break
        except Exception as exc:
            logger.warning("solver._explore: %s", exc)

        return "\n".join(context_parts)

    def _plan(self, bounty, solution, repo_context: str) -> str:
        """Use AI to generate implementation plan."""
        prompt = f"""You are an expert software engineer. Create a step-by-step implementation plan to fix this GitHub bounty issue.

{repo_context}

Provide a numbered implementation plan with:
1. Which files to modify and why
2. Exact changes needed
3. Tests to add or update
4. Edge cases to handle

Be specific and actionable. Focus only on changes needed to fix this issue."""

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.config.get("ANTHROPIC_API_KEY", ""))
            resp = client.messages.create(
                model=self.config.get("AI_MODEL") or "claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as exc:
            logger.warning("solver._plan: AI failed: %s", exc)
            return f"Manual implementation plan needed for: {bounty.title}\n\nDescription:\n{bounty.description[:500]}"

    def _code(self, bounty, solution, plan: str):
        """Run Claude Code CLI or fallback to API code generation."""
        coding_agent = self.config.get("CODING_AGENT", "claude")
        if coding_agent == "claude" and self._claude_code_available():
            self._run_claude_code(bounty, solution, plan)
        else:
            self._run_ai_codegen(bounty, solution, plan)

    def _claude_code_available(self) -> bool:
        try:
            r = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _run_claude_code(self, bounty, solution, plan: str):
        """Invoke Claude Code CLI to implement the fix."""
        if not solution.local_path:
            logger.warning("solver: no local_path set on solution, skipping claude code")
            return
        task = f"""Fix the following GitHub issue in this repository:

Title: {bounty.title}
Issue: {bounty.description[:1000]}

Implementation Plan:
{plan}

Requirements:
- Only modify files directly related to fixing this issue
- Ensure all existing tests still pass
- Add tests for your changes
- Follow the existing code style"""

        try:
            result = subprocess.run(
                ["claude", "--print", task],
                cwd=solution.local_path,
                capture_output=True, text=True, timeout=3600,
            )
            if result.returncode == 0:
                solution.diff_summary = result.stdout[:2000]
                solution.save(update_fields=["diff_summary"])
            else:
                logger.warning("solver._run_claude_code: exit %d: %s", result.returncode, result.stderr[:500])
        except Exception as exc:
            logger.warning("solver._run_claude_code: %s", exc)

    def _run_ai_codegen(self, bounty, solution, plan: str):
        """Fallback: use AI API to generate code changes description."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.config.get("ANTHROPIC_API_KEY", ""))
            prompt = f"""Generate the code changes needed to fix this GitHub issue.

{bounty.title}

{bounty.description[:1000]}

Plan:
{plan}

Provide a unified diff format showing exactly what needs to change."""
            resp = client.messages.create(
                model=self.config.get("AI_MODEL") or "claude-sonnet-4-20250514",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            solution.diff_summary = resp.content[0].text[:2000]
            solution.save(update_fields=["diff_summary"])
        except Exception as exc:
            logger.warning("solver._run_ai_codegen: %s", exc)

    def _test(self, solution):
        """Run test suite in solution's local path."""
        if not solution.local_path:
            solution.all_tests_pass = False
            solution.save(update_fields=["all_tests_pass"])
            return
        try:
            result = subprocess.run(
                ["pytest", "--tb=short", "-q"],
                cwd=solution.local_path,
                capture_output=True, text=True, timeout=300,
            )
            solution.all_tests_pass = result.returncode == 0
            solution.save(update_fields=["all_tests_pass"])
            if not solution.all_tests_pass:
                logger.warning("solver._test: tests failed:\n%s", result.stdout[-1000:])
        except Exception as exc:
            logger.warning("solver._test: %s", exc)
            solution.all_tests_pass = False
            solution.save(update_fields=["all_tests_pass"])

    def _review(self, bounty, solution) -> tuple[bool, str]:
        """Internal AI review of the solution."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.config.get("ANTHROPIC_API_KEY", ""))
            prompt = f"""Review this proposed fix for a GitHub issue.

Issue: {bounty.title}
Description: {bounty.description[:500]}

Proposed changes:
{solution.diff_summary or solution.implementation_plan or "No diff available"}

Files changed: {', '.join(solution.files_changed or [])}
All tests pass: {solution.all_tests_pass}

Evaluate:
1. Does the fix actually address the issue?
2. Are there any edge cases missed?
3. Is the scope appropriate (not changing too many things)?
4. Are there any obvious bugs?

Respond with:
APPROVED: <brief reason>
or
CHANGES_NEEDED: <specific feedback>"""

            resp = client.messages.create(
                model=self.config.get("AI_MODEL") or "claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            if text.upper().startswith("APPROVED"):
                return True, text
            return False, text
        except Exception as exc:
            logger.warning("solver._review: AI failed: %s", exc)
            # If review fails and tests pass, approve cautiously
            return solution.all_tests_pass, "Review unavailable — approved based on test results"
