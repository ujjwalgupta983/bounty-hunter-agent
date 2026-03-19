"""
Management command: cleanup

Remove old rejected, abandoned, and expired bounties from the database.

Usage:
    python manage.py cleanup
    python manage.py cleanup --older-than 30
    python manage.py cleanup --dry-run
    python manage.py cleanup --older-than 60 --dry-run
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete old rejected, abandoned, and expired bounties"

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=90,
            dest="older_than",
            help="Delete bounties older than this many days (default: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview what would be deleted without actually deleting anything",
        )

    def handle(self, *args, **options):
        from bounty_hunter.models.models import Bounty, BountyStatus

        older_than = options["older_than"]
        dry_run = options["dry_run"]

        cutoff = timezone.now() - datetime.timedelta(days=older_than)
        terminal_statuses = [
            BountyStatus.REJECTED,
            BountyStatus.ABANDONED,
            BountyStatus.EXPIRED,
        ]

        qs = Bounty.objects.filter(
            status__in=terminal_statuses,
            discovered_at__lt=cutoff,
        )

        total = qs.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN — would delete {total} bounty record(s) "
                f"(status in rejected/abandoned/expired, older than {older_than} days)"
            ))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"Cleaning up bounties older than {older_than} days "
                f"with terminal statuses..."
            ))

        if total == 0:
            self.stdout.write("  Nothing to clean up.")
            self.stdout.write("")
            return

        # Show breakdown by status before deletion
        breakdown = {}
        for status in terminal_statuses:
            count = qs.filter(status=status).count()
            if count > 0:
                breakdown[status] = count

        for status, count in breakdown.items():
            self.stdout.write(f"  {status:<15} : {count} bounty record(s)")

        if dry_run:
            self.stdout.write("")
            self.stdout.write("  (No records were deleted — remove --dry-run to delete)")
            self.stdout.write("")
            return

        # Perform deletion
        deleted_count, _ = qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"\n  Deleted {deleted_count} bounty record(s) successfully."
        ))
        self.stdout.write("")
