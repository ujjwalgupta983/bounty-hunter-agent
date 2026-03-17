from rest_framework import serializers
from bounty_hunter.models.models import Bounty, Evaluation, Solution, Submission, Earning


class EvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evaluation
        fields = "__all__"


class BountyListSerializer(serializers.ModelSerializer):
    roi_score = serializers.FloatField(source="evaluation.roi_score", read_only=True, default=None)
    estimated_hours = serializers.FloatField(source="evaluation.estimated_hours", read_only=True, default=None)
    effective_hourly_rate = serializers.DecimalField(
        source="evaluation.effective_hourly_rate", max_digits=10, decimal_places=2, read_only=True, default=None
    )

    class Meta:
        model = Bounty
        fields = [
            "id", "platform", "title", "repo_owner", "repo_name",
            "bounty_amount_usd", "language", "status", "source_url",
            "competitors_count", "discovered_at", "roi_score",
            "estimated_hours", "effective_hourly_rate",
        ]


class BountyDetailSerializer(serializers.ModelSerializer):
    evaluation = EvaluationSerializer(read_only=True)

    class Meta:
        model = Bounty
        fields = "__all__"


class SubmissionSerializer(serializers.ModelSerializer):
    bounty_title = serializers.CharField(source="bounty.title", read_only=True)
    bounty_amount = serializers.DecimalField(source="bounty.bounty_amount_usd", max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Submission
        fields = "__all__"


class EarningSerializer(serializers.ModelSerializer):
    bounty_title = serializers.CharField(source="bounty.title", read_only=True)
    platform = serializers.CharField(source="bounty.platform", read_only=True)

    class Meta:
        model = Earning
        fields = "__all__"
