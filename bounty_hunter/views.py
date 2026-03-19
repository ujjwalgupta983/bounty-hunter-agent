from django.shortcuts import render
from django.views import View
from django.db.models import Sum


class DashboardView(View):
    def get(self, request):
        from bounty_hunter.models.models import Bounty, BountyStatus, Earning

        stats = {
            "total": Bounty.objects.count(),
            "active": Bounty.objects.filter(
                status__in=[BountyStatus.TARGETED, BountyStatus.IN_PROGRESS]
            ).count(),
            "submitted": Bounty.objects.filter(status=BountyStatus.SUBMITTED).count(),
            "merged": Bounty.objects.filter(status=BountyStatus.MERGED).count(),
            "earned": Earning.objects.aggregate(total=Sum("net_earning_usd"))["total"] or 0,
        }
        top_bounties = (
            Bounty.objects.select_related("evaluation")
            .order_by("-bounty_amount_usd")[:20]
        )
        return render(request, "dashboard/index.html", {
            "stats": stats,
            "bounties": top_bounties,
        })


# Keep backward-compatible function alias
def dashboard(request):
    return DashboardView.as_view()(request)
