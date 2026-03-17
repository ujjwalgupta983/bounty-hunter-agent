"""
Django admin registration for all Bounty Hunter models.
"""
from django.contrib import admin
from django.utils.html import format_html

from bounty_hunter.models.models import Bounty, Evaluation, Solution, Submission, Earning, ScanLog


@admin.register(Bounty)
class BountyAdmin(admin.ModelAdmin):
    list_display = [
        "title_short", "platform", "bounty_amount_usd", "status",
        "language", "competitors_count", "existing_prs", "discovered_at",
    ]
    list_filter = ["platform", "status", "language"]
    search_fields = ["title", "repo_owner", "repo_name", "description"]
    ordering = ["-discovered_at"]
    readonly_fields = ["discovered_at", "updated_at", "repo_full_name"]
    list_select_related = True

    def title_short(self, obj):
        return obj.title[:80]
    title_short.short_description = "Title"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("evaluation")


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = [
        "bounty_title", "roi_score", "estimated_difficulty", "estimated_hours",
        "effective_hourly_rate", "tech_match_score", "auto_rejected", "evaluated_at",
    ]
    list_filter = ["estimated_difficulty", "auto_rejected", "has_tests", "has_ci"]
    search_fields = ["bounty__title", "analysis_summary", "rejection_reason"]
    ordering = ["-roi_score"]
    readonly_fields = ["evaluated_at"]

    def bounty_title(self, obj):
        return obj.bounty.title[:80]
    bounty_title.short_description = "Bounty"


@admin.register(Solution)
class SolutionAdmin(admin.ModelAdmin):
    list_display = [
        "bounty_title", "status", "iteration_count", "all_tests_pass",
        "lint_clean", "review_approved", "time_spent_hours", "agent_cost_usd", "started_at",
    ]
    list_filter = ["status", "all_tests_pass", "lint_clean", "review_approved"]
    search_fields = ["bounty__title", "branch_name", "implementation_plan"]
    ordering = ["-started_at"]
    readonly_fields = ["started_at", "completed_at", "time_spent_hours"]

    def bounty_title(self, obj):
        return obj.bounty.title[:80]
    bounty_title.short_description = "Bounty"


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "pr_title_short", "bounty_link", "pr_status", "bounty_claimed",
        "response_count", "submitted_at", "merged_at",
    ]
    list_filter = ["pr_status", "bounty_claimed"]
    search_fields = ["pr_title", "pr_body", "bounty__title"]
    ordering = ["-submitted_at"]
    readonly_fields = ["submitted_at", "last_checked_at", "merged_at"]

    def pr_title_short(self, obj):
        return obj.pr_title[:80]
    pr_title_short.short_description = "PR Title"

    def bounty_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.bounty.source_url, obj.bounty.title[:60])
    bounty_link.short_description = "Bounty"


@admin.register(Earning)
class EarningAdmin(admin.ModelAdmin):
    list_display = [
        "bounty_title", "amount_usd", "platform_fee_usd", "agent_cost_usd",
        "net_earning_usd", "effective_hourly_rate", "payment_status", "earned_at",
    ]
    list_filter = ["payment_status"]
    search_fields = ["bounty__title", "payment_method", "payment_reference"]
    ordering = ["-earned_at"]
    readonly_fields = ["earned_at", "paid_at"]

    def bounty_title(self, obj):
        return obj.bounty.title[:80]
    bounty_title.short_description = "Bounty"


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = [
        "platform", "bounties_found", "bounties_new", "bounties_updated",
        "success", "started_at", "completed_at",
    ]
    list_filter = ["platform", "success"]
    ordering = ["-started_at"]
    readonly_fields = ["started_at", "completed_at"]
