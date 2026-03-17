from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BountyViewSet, EvaluationViewSet, SubmissionViewSet, EarningViewSet, DashboardView

router = DefaultRouter()
router.register(r"bounties", BountyViewSet)
router.register(r"evaluations", EvaluationViewSet)
router.register(r"submissions", SubmissionViewSet)
router.register(r"earnings", EarningViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("scout/scan/", lambda r: __import__("bounty_hunter.scouts.tasks", fromlist=["run_full_scan"]).run_full_scan.delay() or __import__("rest_framework.response", fromlist=["Response"]).Response({"status": "scan_triggered"}), name="trigger-scan"),
]
