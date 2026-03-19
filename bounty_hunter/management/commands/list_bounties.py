"""
Management command: list_bounties

List discovered bounties with optional filters.

Usage:
    python manage.py list_bounties
    python manage.py list_bounties --status evaluated
    python manage.py list_bounties --status targeted --limit 10
    python manage.py list_bounties --platform github --min-roi 20
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "List bounties with optional filters for status, platform, ROI, and count"

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            type=str,
            default=None,
            help="Filter by bounty status (e.g. discovered, evaluated, targeted, in_progress, "
                 "solved, submitted, merged, paid, rejected, abandoned, expired). "
                 "Default: all statuses.",
        )
        parser.add_argument(
            "--min-roi",
            type=float,
            default=None,
            dest="min_roi",
            help="Only show bounties with ROI score >= this value (requires evaluation).",
        )
        parser.add_argument(
            "--platform",
            type=str,
            default=None,
            help="Filter by platform (e.g. github, algora, opire).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of bounties to show (default: 20, 0 = no limit).",
        )

    def handle(self, *args, **options):
        from bounty_hunter.models.models import Bounty, BountyStatus

        status_filter = options["status"]
        min_roi = options["min_roi"]
        platform_filter = options["platform"]
        limit = options["limit"]

        # Validate status if provided
        valid_statuses = [choice[0] for choice in BountyStatus.choices]
        if status_filter and status_filter not in valid_statuses:
            self.stderr.write(self.style.ERROR(
                f"Invalid status '{status_filter}'. Valid choices: {', '.join(valid_statuses)}"
            ))
            return

        qs = Bounty.objects.select_related("evaluation").order_by("-discovered_at")

        if status_filter:
            qs = qs.filter(status=status_filter)

        if platform_filter:
            qs = qs.filter(platform__iexact=platform_filter)

        if min_roi is not None:
            # Only bounties that have an evaluation with roi_score >= min_roi
            qs = qs.filter(evaluation__roi_score__gte=min_roi)

        total = qs.count()

        if limit > 0:
            qs = qs[:limit]

        bounties = list(qs)

        if not bounties:
            self.stdout.write("No bounties found matching the given filters.")
            return

        # Table header
        col_id = 6
        col_platform = 10
        col_amount = 10
        col_status = 14
        col_roi = 7
        col_title = 50

        sep = (
            f"{'─' * col_id}-{'─' * col_platform}-{'─' * col_amount}-"
            f"{'─' * col_status}-{'─' * col_roi}-{'─' * col_title}"
        )

        header = (
            f"{'ID':<{col_id}} {'Platform':<{col_platform}} {'Amount ($)':<{col_amount}} "
            f"{'Status':<{col_status}} {'ROI':>{col_roi}} {'Title':<{col_title}}"
        )

        self.stdout.write("")
        self.stdout.write(header)
        self.stdout.write(sep)

        for bounty in bounties:
            eval_obj = getattr(bounty, "evaluation", None)
            roi_str = f"{eval_obj.roi_score:.1f}" if eval_obj and not eval_obj.auto_rejected else "-"
            amount_str = f"{bounty.bounty_amount_usd:,.2f}"
            title = bounty.title[:col_title]

            self.stdout.write(
                f"{bounty.id:<{col_id}} {bounty.platform:<{col_platform}} "
                f"{amount_str:<{col_amount}} {bounty.status:<{col_status}} "
                f"{roi_str:>{col_roi}} {title}"
            )

        self.stdout.write(sep)

        shown = len(bounties)
        if limit > 0 and total > limit:
            self.stdout.write(f"Showing {shown} of {total} bounties (use --limit to see more)")
        else:
            self.stdout.write(f"Total: {total} bounties")

        self.stdout.write("")
