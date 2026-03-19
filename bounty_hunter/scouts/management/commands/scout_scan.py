"""
Management command: scout_scan

Run a bounty scout scan immediately (bypassing Celery).
Useful for local dev and one-shot testing.

Usage:
    python manage.py scout_scan
    python manage.py scout_scan --platform github
    python manage.py scout_scan --platform algora
"""
import time

from django.core.management.base import BaseCommand, CommandError

from bounty_hunter.scouts.github_scout import GitHubScout
from bounty_hunter.scouts.algora_scout import AlgoraScout
from bounty_hunter.scouts.opire_scout import OpireScout
from bounty_hunter.scouts.issuehunt_scout import IssueHuntScout
from bounty_hunter.analyst.tasks import evaluate_new_bounties


SCOUTS = {
    "github": GitHubScout,
    "algora": AlgoraScout,
    "opire": OpireScout,
    "issuehunt": IssueHuntScout,
}


class Command(BaseCommand):
    help = "Run bounty scout scan for one or all platforms"

    def add_arguments(self, parser):
        parser.add_argument(
            "--platform",
            choices=list(SCOUTS.keys()),
            default=None,
            help="Specific platform to scan (default: all)",
        )
        parser.add_argument(
            "--no-evaluate",
            action="store_true",
            default=False,
            help="Skip analyst evaluation after scanning",
        )

    def handle(self, *args, **options):
        platform = options["platform"]
        skip_eval = options["no_evaluate"]

        platforms_to_scan = [platform] if platform else list(SCOUTS.keys())

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Starting scout scan: {', '.join(platforms_to_scan)}"
        ))

        total_found = 0
        total_new = 0

        for name in platforms_to_scan:
            self.stdout.write(f"  Scanning {name}...", ending=" ")
            t0 = time.time()

            try:
                scout = SCOUTS[name]()
                result = scout.scan()
                elapsed = time.time() - t0

                found = result.get("found", 0)
                new = result.get("new", 0)
                updated = result.get("updated", 0)
                errors = result.get("errors", [])

                total_found += found
                total_new += new

                self.stdout.write(self.style.SUCCESS(
                    f"done ({elapsed:.1f}s) — found={found} new={new} updated={updated}"
                ))

                if errors:
                    for err in errors[:5]:
                        self.stderr.write(f"    ERROR: {err}")

            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"FAILED: {exc}"))
                raise CommandError(f"Scout scan failed for {name}: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(f"\nScan complete — total found: {total_found}, new: {total_new}")
        )

        if not skip_eval and total_new > 0:
            self.stdout.write("  Running analyst evaluation on new bounties...")
            try:
                evaluate_new_bounties()
                self.stdout.write(self.style.SUCCESS("  Evaluation complete."))
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f"  Evaluation failed: {exc}"))
