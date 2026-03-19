"""
Management command: evaluate_bounty

Usage:
    python manage.py evaluate_bounty 42
    python manage.py evaluate_bounty --all
    python manage.py evaluate_bounty --all --status discovered
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Evaluate a bounty (or all unevaluated bounties) using the BountyAnalyst scorer"

    def add_arguments(self, parser):
        parser.add_argument(
            "bounty_id",
            type=int,
            nargs="?",
            help="Database ID of the bounty to evaluate",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            help="Evaluate all DISCOVERED (unevaluated) bounties",
        )
        parser.add_argument(
            "--status",
            default="discovered",
            help="Filter by status when using --all (default: discovered)",
        )

    def handle(self, *args, **options):
        from bounty_hunter.models.models import Bounty
        from bounty_hunter.analyst.scorer import BountyAnalyst

        if options["all"]:
            bounties = Bounty.objects.filter(status=options["status"])
            count = bounties.count()
            if count == 0:
                self.stdout.write(self.style.WARNING(f"No bounties with status '{options['status']}' found."))
                return
            self.stdout.write(self.style.MIGRATE_HEADING(f"Evaluating {count} bounties with status='{options['status']}'..."))
            analyst = BountyAnalyst()
            done, skipped, failed = 0, 0, 0
            for bounty in bounties:
                try:
                    if hasattr(bounty, "evaluation"):
                        skipped += 1
                        continue
                    evaluation = analyst.evaluate(bounty)
                    if evaluation:
                        status = "REJECTED" if evaluation.auto_rejected else f"ROI={evaluation.roi_score:.1f}"
                        self.stdout.write(f"  #{bounty.id} [{status}] {bounty.title[:60]}")
                        done += 1
                except Exception as exc:
                    self.stderr.write(f"  #{bounty.id} FAILED: {exc}")
                    failed += 1
            self.stdout.write(self.style.SUCCESS(f"\nDone: {done} evaluated, {skipped} skipped, {failed} failed."))
            return

        bounty_id = options.get("bounty_id")
        if not bounty_id:
            raise CommandError("Provide a bounty_id or use --all")

        try:
            bounty = Bounty.objects.get(pk=bounty_id)
        except Bounty.DoesNotExist:
            raise CommandError(f"Bounty {bounty_id} does not exist.")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Evaluating bounty #{bounty_id}: {bounty.title[:80]}"))
        self.stdout.write(f"  Platform : {bounty.platform}")
        self.stdout.write(f"  Amount   : ${bounty.bounty_amount_usd}")
        self.stdout.write(f"  Repo     : {bounty.repo_full_name}")

        if hasattr(bounty, "evaluation"):
            self.stdout.write(self.style.WARNING("  Already evaluated — returning existing result."))

        analyst = BountyAnalyst()
        try:
            evaluation = analyst.evaluate(bounty)
        except Exception as exc:
            raise CommandError(f"Evaluation failed: {exc}") from exc

        if not evaluation:
            self.stdout.write(self.style.ERROR("  Evaluation returned None."))
            return

        sep = "─" * 50
        self.stdout.write(sep)
        if evaluation.auto_rejected:
            self.stdout.write(self.style.ERROR(f"  AUTO-REJECTED: {evaluation.rejection_reason}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ROI Score      : {evaluation.roi_score:.1f} / 100"))
            self.stdout.write(f"  Difficulty     : {evaluation.estimated_difficulty} ({evaluation.difficulty_score:.0f}/100)")
            self.stdout.write(f"  Tech Match     : {evaluation.tech_match_score:.0f}/100")
            self.stdout.write(f"  Competition    : {evaluation.competition_score:.0f}/100")
            self.stdout.write(f"  Est. Hours     : {evaluation.estimated_hours:.1f}h")
            self.stdout.write(f"  Effective Rate : ${evaluation.effective_hourly_rate}/hr")
            if evaluation.analysis_summary:
                self.stdout.write(f"  Summary: {evaluation.analysis_summary}")
            if evaluation.risks:
                self.stdout.write(f"  Risks: {', '.join(evaluation.risks)}")
        self.stdout.write(sep)
