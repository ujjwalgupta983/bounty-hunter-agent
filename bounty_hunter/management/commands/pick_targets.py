"""
Management command: pick_targets

Run the bounty picker synchronously (without Celery) to select the top
evaluated bounties and mark them as TARGETED.

Usage:
    python manage.py pick_targets
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the bounty picker to select top ROI targets (synchronous)"

    def handle(self, *args, **options):
        from bounty_hunter.picker.tasks import pick_targets
        from bounty_hunter.models.models import Bounty, BountyStatus
        from django.conf import settings

        config = settings.BOUNTY_HUNTER
        max_concurrent = config["MAX_CONCURRENT_SOLVERS"]
        min_roi = config["MIN_ROI_SCORE"]

        # Show current state before picking
        active_count = Bounty.objects.filter(
            status__in=[BountyStatus.TARGETED, BountyStatus.IN_PROGRESS]
        ).count()
        candidates_count = (
            Bounty.objects
            .filter(status=BountyStatus.EVALUATED)
            .exclude(evaluation__auto_rejected=True)
            .filter(evaluation__roi_score__gte=min_roi)
            .count()
        )

        self.stdout.write(self.style.MIGRATE_HEADING("Running bounty picker..."))
        self.stdout.write(f"  Capacity      : {active_count}/{max_concurrent} slots used")
        self.stdout.write(f"  Min ROI score : {min_roi}")
        self.stdout.write(f"  Candidates    : {candidates_count} evaluated bounties qualify")
        self.stdout.write("")

        if active_count >= max_concurrent:
            self.stdout.write(self.style.WARNING(
                f"  At capacity ({active_count}/{max_concurrent}) — no new targets will be picked."
            ))
            return

        # Capture the IDs that are currently targeted so we can diff after
        targeted_before = set(
            Bounty.objects.filter(status=BountyStatus.TARGETED).values_list("id", flat=True)
        )

        try:
            result = pick_targets()
        except Exception as exc:
            raise CommandError(f"pick_targets failed: {exc}") from exc

        picked = result.get("picked", 0)

        # Find newly targeted bounties
        newly_targeted = (
            Bounty.objects
            .filter(status=BountyStatus.TARGETED)
            .exclude(id__in=targeted_before)
            .select_related("evaluation")
        )

        if picked == 0:
            self.stdout.write(self.style.WARNING(
                f"  No new targets picked. reason={result.get('reason', 'unknown')}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Picked {picked} new target(s):"))
            self.stdout.write("")
            for bounty in newly_targeted:
                roi = getattr(getattr(bounty, "evaluation", None), "roi_score", None)
                roi_str = f"ROI:{roi:.1f}" if roi is not None else "ROI:n/a"
                self.stdout.write(
                    f"  #{bounty.id:<6} ${bounty.bounty_amount_usd:<10} {roi_str:<12} "
                    f"[{bounty.platform}] {bounty.title[:60]}"
                )

        self.stdout.write("")
