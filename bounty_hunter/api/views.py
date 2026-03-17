from rest_framework import viewsets, views
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Count, Q, Avg

from bounty_hunter.models.models import Bounty, Evaluation, Submission, Earning, BountyStatus
from .serializers import (
    BountyListSerializer, BountyDetailSerializer,
    EvaluationSerializer, SubmissionSerializer, EarningSerializer,
)


class BountyViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for bounties."""
    queryset = Bounty.objects.select_related("evaluation").all()
    filterset_fields = ["platform", "status", "language"]
    search_fields = ["title", "description", "repo_owner", "repo_name"]
    ordering_fields = ["bounty_amount_usd", "discovered_at", "evaluation__roi_score"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BountyDetailSerializer
        return BountyListSerializer

    @action(detail=False, methods=["get"])
    def top_opportunities(self, request):
        """Get top bounties by ROI score."""
        limit = int(request.query_params.get("limit", 10))
        bounties = (
            self.queryset
            .filter(status=BountyStatus.EVALUATED)
            .exclude(evaluation__auto_rejected=True)
            .order_by("-evaluation__roi_score")
            [:limit]
        )
        serializer = BountyListSerializer(bounties, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def active(self, request):
        """Get bounties currently being worked on."""
        bounties = self.queryset.filter(
            status__in=[BountyStatus.TARGETED, BountyStatus.IN_PROGRESS, BountyStatus.SUBMITTED]
        )
        serializer = BountyListSerializer(bounties, many=True)
        return Response(serializer.data)


class EvaluationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Evaluation.objects.select_related("bounty").all()
    serializer_class = EvaluationSerializer
    filterset_fields = ["estimated_difficulty", "auto_rejected"]
    ordering_fields = ["roi_score", "estimated_hours", "effective_hourly_rate"]


class SubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Submission.objects.select_related("bounty").all()
    serializer_class = SubmissionSerializer
    filterset_fields = ["pr_status", "bounty_claimed"]
    ordering_fields = ["submitted_at"]


class EarningViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Earning.objects.select_related("bounty").all()
    serializer_class = EarningSerializer
    filterset_fields = ["payment_status"]
    ordering_fields = ["amount_usd", "earned_at"]


class DashboardView(views.APIView):
    """Aggregated dashboard stats."""

    def get(self, request):
        total_bounties = Bounty.objects.count()
        by_status = dict(
            Bounty.objects.values_list("status").annotate(count=Count("id")).values_list("status", "count")
        )

        # Earnings
        earnings_agg = Earning.objects.aggregate(
            total_earned=Sum("net_earning_usd"),
            total_pending=Sum("net_earning_usd", filter=Q(payment_status="pending")),
            total_paid=Sum("net_earning_usd", filter=Q(payment_status="paid")),
            avg_earning=Avg("net_earning_usd"),
            avg_hourly_rate=Avg("effective_hourly_rate"),
        )

        # Submissions
        submissions_agg = Submission.objects.aggregate(
            total_submitted=Count("id"),
            total_merged=Count("id", filter=Q(pr_status="merged")),
            total_rejected=Count("id", filter=Q(pr_status__in=["rejected", "closed"])),
            total_pending=Count("id", filter=Q(pr_status__in=["submitted", "review_requested", "changes_requested"])),
        )

        # Win rate
        total_attempted = submissions_agg["total_submitted"] or 0
        total_won = submissions_agg["total_merged"] or 0
        win_rate = (total_won / total_attempted * 100) if total_attempted > 0 else 0

        return Response({
            "bounties": {
                "total": total_bounties,
                "by_status": by_status,
            },
            "submissions": submissions_agg,
            "earnings": earnings_agg,
            "performance": {
                "win_rate": round(win_rate, 1),
                "total_attempted": total_attempted,
                "total_won": total_won,
            },
        })
