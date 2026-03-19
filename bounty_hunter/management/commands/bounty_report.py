"""
Management command: bounty_report

Prints a summary report of bounty hunting activity.

Usage:
    python manage.py bounty_report
    python manage.py bounty_report --days 7
    python manage.py bounty_report --days 0   # all time
    python manage.py bounty_report --json
    python manage.py bounty_report --days 7 --json
"""
import json

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
import datetime


class Command(BaseCommand):
    help = "Print a bounty hunting activity report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days to include in report (0 = all time, default: 30)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            dest="output_json",
            help="Output report data as JSON instead of a human-readable table",
        )

    def handle(self, *args, **options):
        from bounty_hunter.models.models import Bounty, Submission, Earning, BountyStatus

        days = options["days"]
        output_json = options["output_json"]

        if days > 0:
            since = timezone.now() - datetime.timedelta(days=days)
            bounties_qs = Bounty.objects.filter(discovered_at__gte=since)
            submissions_qs = Submission.objects.filter(submitted_at__gte=since)
            earnings_qs = Earning.objects.filter(earned_at__gte=since)
            period_label = f"Last {days} Days"
        else:
            bounties_qs = Bounty.objects.all()
            submissions_qs = Submission.objects.all()
            earnings_qs = Earning.objects.all()
            period_label = "All Time"

        # Bounty counts
        total_bounties = bounties_qs.count()
        total_evaluated = bounties_qs.filter(status__in=[
            BountyStatus.EVALUATED, BountyStatus.TARGETED, BountyStatus.IN_PROGRESS,
            BountyStatus.SOLVED, BountyStatus.SUBMITTED, BountyStatus.MERGED, BountyStatus.PAID,
        ]).count()
        total_targeted = bounties_qs.filter(status__in=[
            BountyStatus.TARGETED, BountyStatus.IN_PROGRESS, BountyStatus.SOLVED,
            BountyStatus.SUBMITTED, BountyStatus.MERGED, BountyStatus.PAID,
        ]).count()

        # Submission counts
        total_submitted = submissions_qs.count()
        total_merged = submissions_qs.filter(pr_status="merged").count()
        total_pending = submissions_qs.filter(pr_status__in=[
            "submitted", "review_requested", "changes_requested"
        ]).count()
        total_rejected = submissions_qs.filter(pr_status__in=["closed", "rejected"]).count()

        win_rate = (total_merged / total_submitted * 100) if total_submitted > 0 else 0.0

        # Earnings
        earnings_agg = earnings_qs.aggregate(
            confirmed=Sum("net_earning_usd", filter=Q(payment_status="paid")),
            pending=Sum("net_earning_usd", filter=Q(payment_status__in=["pending", "processing"])),
            avg_earning=Avg("net_earning_usd", filter=Q(payment_status="paid")),
            avg_hours=Avg("total_time_hours"),
            avg_hourly=Avg("effective_hourly_rate", filter=Q(payment_status="paid")),
        )

        confirmed = earnings_agg["confirmed"] or 0
        pending_earn = earnings_agg["pending"] or 0
        avg_earn = earnings_agg["avg_earning"] or 0
        avg_hours = earnings_agg["avg_hours"] or 0
        avg_hourly = earnings_agg["avg_hourly"] or 0

        # By platform breakdown
        by_platform = (
            bounties_qs
            .values("platform")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Build data structure (used for both JSON and human output)
        report_data = {
            "period": period_label,
            "days": days,
            "bounties": {
                "scraped": total_bounties,
                "evaluated": total_evaluated,
                "attempted": total_targeted,
            },
            "submissions": {
                "total": total_submitted,
                "merged": total_merged,
                "pending": total_pending,
                "rejected": total_rejected,
                "win_rate_pct": round(win_rate, 1),
            },
            "earnings": {
                "confirmed_usd": float(confirmed),
                "pending_usd": float(pending_earn),
                "pipeline_usd": float(confirmed + pending_earn),
                "avg_per_bounty_usd": float(avg_earn) if total_merged > 0 else None,
                "avg_hours": float(avg_hours) if total_merged > 0 else None,
                "effective_hourly_rate_usd": float(avg_hourly) if total_merged > 0 else None,
            },
            "by_platform": [
                {"platform": row["platform"], "count": row["count"]}
                for row in by_platform
            ],
        }

        if output_json:
            self.stdout.write(json.dumps(report_data, indent=2))
            return

        # Print human-readable report
        sep = "─" * 45
        self.stdout.write(f"\n{'Bounty Hunter Report':^45}")
        self.stdout.write(f"{'(' + period_label + ')':^45}")
        self.stdout.write(sep)

        self.stdout.write(f"{'Bounties Scraped:':<30} {total_bounties:>10}")
        self.stdout.write(f"{'Bounties Evaluated:':<30} {total_evaluated:>10}")
        self.stdout.write(f"{'Bounties Attempted:':<30} {total_targeted:>10}")
        self.stdout.write(sep)

        self.stdout.write(f"{'PRs Submitted:':<30} {total_submitted:>10}")
        self.stdout.write(f"{'PRs Merged:':<30} {total_merged:>10}")
        self.stdout.write(f"{'PRs Pending Review:':<30} {total_pending:>10}")
        self.stdout.write(f"{'PRs Rejected/Closed:':<30} {total_rejected:>10}")
        self.stdout.write(f"{'Win Rate:':<30} {win_rate:>9.1f}%")
        self.stdout.write(sep)

        self.stdout.write(f"{'Earnings (Confirmed):':<30} ${confirmed:>9,.2f}")
        self.stdout.write(f"{'Earnings (Pending):':<30} ${pending_earn:>9,.2f}")
        self.stdout.write(f"{'Total Pipeline:':<30} ${confirmed + pending_earn:>9,.2f}")
        if total_merged > 0:
            self.stdout.write(f"{'Avg $/Bounty Won:':<30} ${avg_earn:>9,.2f}")
            self.stdout.write(f"{'Avg Hours/Bounty:':<30} {avg_hours:>9.1f}h")
            self.stdout.write(f"{'Effective Rate:':<30} ${avg_hourly:>8,.0f}/hr")
        self.stdout.write(sep)

        if by_platform:
            self.stdout.write("\nBy Platform:")
            for row in by_platform:
                self.stdout.write(f"  {row['platform']:<20} {row['count']:>6} bounties")

        self.stdout.write("")
