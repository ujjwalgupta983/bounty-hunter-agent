"""
Core models for the Bounty Hunter Agent.

Data flows: Bounty → Evaluation → Target → Solution → Submission → Tracking
"""
from django.db import models
from django.utils import timezone


class Platform(models.TextChoices):
    GITHUB = "github", "GitHub Issues"
    ALGORA = "algora", "Algora"
    OPIRE = "opire", "Opire"
    GITCOIN = "gitcoin", "Gitcoin"
    ISSUEHUNT = "issuehunt", "IssueHunt"
    HACKERONE = "hackerone", "HackerOne"
    BUGCROWD = "bugcrowd", "Bugcrowd"
    IMMUNEFI = "immunefi", "Immunefi"
    CODE4RENA = "code4rena", "Code4rena"
    OTHER = "other", "Other"


class BountyStatus(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    EVALUATED = "evaluated", "Evaluated"
    TARGETED = "targeted", "Targeted"
    IN_PROGRESS = "in_progress", "In Progress"
    SOLVED = "solved", "Solved"
    SUBMITTED = "submitted", "PR Submitted"
    MERGED = "merged", "PR Merged"
    PAID = "paid", "Paid"
    REJECTED = "rejected", "Rejected"
    ABANDONED = "abandoned", "Abandoned"
    EXPIRED = "expired", "Expired"


class Difficulty(models.TextChoices):
    TRIVIAL = "trivial", "Trivial"
    EASY = "easy", "Easy"
    MEDIUM = "medium", "Medium"
    HARD = "hard", "Hard"
    EXPERT = "expert", "Expert"


class PaymentMethod(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    CRYPTO = "crypto", "Crypto"
    PAYPAL = "paypal", "PayPal"
    UNKNOWN = "unknown", "Unknown"


class Bounty(models.Model):
    """A bounty discovered from any platform."""

    # Identity
    external_id = models.CharField(max_length=255, help_text="Platform-specific ID")
    platform = models.CharField(max_length=20, choices=Platform.choices)
    source_url = models.URLField(max_length=500)

    # Issue details
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    repo_owner = models.CharField(max_length=255)
    repo_name = models.CharField(max_length=255)
    repo_url = models.URLField(max_length=500)
    issue_number = models.IntegerField(null=True, blank=True)

    # Bounty specifics
    bounty_amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=10, blank=True, default="")
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.UNKNOWN
    )
    india_payable = models.BooleanField(
        default=False, help_text="True if payment_method is bank_transfer or crypto"
    )

    # Metadata
    labels = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=50, blank=True, default="")
    languages = models.JSONField(default=list, blank=True, help_text="All languages in repo")
    deadline = models.DateTimeField(null=True, blank=True)
    competitors_count = models.IntegerField(default=0, help_text="Number of people working on this")
    existing_prs = models.IntegerField(default=0, help_text="PRs already submitted")

    # Status tracking
    status = models.CharField(max_length=20, choices=BountyStatus.choices, default=BountyStatus.DISCOVERED)

    # Timestamps
    posted_at = models.DateTimeField(null=True, blank=True)
    discovered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "bounties"
        unique_together = ["platform", "external_id"]
        ordering = ["-discovered_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["platform", "status"]),
            models.Index(fields=["bounty_amount_usd"]),
            models.Index(fields=["-discovered_at"]),
        ]

    def __str__(self):
        return f"[{self.platform}] ${self.bounty_amount_usd} — {self.title[:80]}"

    @property
    def repo_full_name(self):
        return f"{self.repo_owner}/{self.repo_name}"


class Evaluation(models.Model):
    """AI-generated evaluation of a bounty's feasibility and ROI."""

    bounty = models.OneToOneField(Bounty, on_delete=models.CASCADE, related_name="evaluation")

    # Scores (0-100)
    roi_score = models.FloatField(help_text="Overall ROI score 0-100")
    difficulty_score = models.FloatField(help_text="Difficulty 0-100 (lower = easier)")
    tech_match_score = models.FloatField(help_text="How well our stack matches 0-100")
    competition_score = models.FloatField(help_text="Competition factor 0-100 (lower = less competition)")
    repo_quality_score = models.FloatField(help_text="Repo quality 0-100")

    # Estimates
    estimated_hours = models.FloatField(help_text="Estimated hours to complete")
    estimated_difficulty = models.CharField(max_length=10, choices=Difficulty.choices)
    effective_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="$/hr if we win")

    # AI analysis
    analysis_summary = models.TextField(help_text="AI's analysis of the issue")
    approach_suggestion = models.TextField(blank=True, default="", help_text="Suggested approach")
    risks = models.JSONField(default=list, help_text="Identified risks")
    required_skills = models.JSONField(default=list)

    # Flags
    has_clear_requirements = models.BooleanField(default=True)
    has_tests = models.BooleanField(default=False, help_text="Repo has test suite")
    has_ci = models.BooleanField(default=False, help_text="Repo has CI/CD")
    has_contribution_guide = models.BooleanField(default=False)
    auto_rejected = models.BooleanField(default=False)
    rejection_reason = models.CharField(max_length=255, blank=True, default="")
    needs_reeval = models.BooleanField(default=False, help_text="AI analysis failed, using defaults")

    # Timestamps
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-roi_score"]

    def __str__(self):
        return f"Eval: {self.bounty.title[:60]} — ROI: {self.roi_score:.1f}"


class Solution(models.Model):
    """A solution being worked on by the solver swarm."""

    bounty = models.ForeignKey(Bounty, on_delete=models.CASCADE, related_name="solutions")

    # Git details
    fork_url = models.URLField(max_length=500, blank=True, default="")
    branch_name = models.CharField(max_length=255, blank=True, default="")
    local_path = models.CharField(max_length=500, blank=True, default="")

    # Solution details
    implementation_plan = models.TextField(blank=True, default="")
    files_changed = models.JSONField(default=list)
    diff_summary = models.TextField(blank=True, default="")
    tests_added = models.JSONField(default=list)

    # Status
    class SolverStatus(models.TextChoices):
        EXPLORING = "exploring", "Exploring Codebase"
        PLANNING = "planning", "Planning Implementation"
        CODING = "coding", "Coding Solution"
        TESTING = "testing", "Running Tests"
        REVIEWING = "reviewing", "Internal Review"
        ITERATING = "iterating", "Iterating on Feedback"
        READY = "ready", "Ready for Submission"
        FAILED = "failed", "Failed"

    status = models.CharField(max_length=20, choices=SolverStatus.choices, default=SolverStatus.EXPLORING)
    iteration_count = models.IntegerField(default=0)
    max_iterations = models.IntegerField(default=3)

    # Quality checks
    all_tests_pass = models.BooleanField(default=False)
    lint_clean = models.BooleanField(default=False)
    review_approved = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True, default="")

    # Time tracking
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.IntegerField(default=0)
    agent_cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0, help_text="AI inference cost")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Solution: {self.bounty.title[:60]} — {self.status}"

    @property
    def time_spent_hours(self):
        return self.time_spent_seconds / 3600


class Submission(models.Model):
    """A PR submission for a bounty."""

    bounty = models.ForeignKey(Bounty, on_delete=models.CASCADE, related_name="submissions")
    solution = models.OneToOneField(Solution, on_delete=models.CASCADE, related_name="submission")

    # PR details
    pr_url = models.URLField(max_length=500)
    pr_number = models.IntegerField()
    pr_title = models.CharField(max_length=500)
    pr_body = models.TextField()

    # Status
    class PRStatus(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEW_REQUESTED = "review_requested", "Review Requested"
        CHANGES_REQUESTED = "changes_requested", "Changes Requested"
        APPROVED = "approved", "Approved"
        MERGED = "merged", "Merged"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"

    pr_status = models.CharField(max_length=20, choices=PRStatus.choices, default=PRStatus.SUBMITTED)
    review_comments = models.JSONField(default=list, help_text="Review comments received")
    response_count = models.IntegerField(default=0, help_text="Times we've responded to reviews")

    # Bounty claim
    bounty_claimed = models.BooleanField(default=False)
    bounty_claim_url = models.URLField(max_length=500, blank=True, default="")

    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(auto_now=True)
    merged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"PR #{self.pr_number}: {self.pr_title[:60]} — {self.pr_status}"


class Earning(models.Model):
    """Track actual earnings from bounties."""

    bounty = models.OneToOneField(Bounty, on_delete=models.CASCADE, related_name="earning")
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="earning")

    # Financials
    amount_usd = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    agent_cost_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_earning_usd = models.DecimalField(max_digits=10, decimal_places=2)

    # Payment
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PAID = "paid", "Paid"
        DISPUTED = "disputed", "Disputed"

    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_method = models.CharField(max_length=50, blank=True, default="")
    payment_reference = models.CharField(max_length=255, blank=True, default="")

    # Time metrics
    total_time_hours = models.FloatField(help_text="Total hours from discovery to merge")
    effective_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)

    # Timestamps
    earned_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-earned_at"]

    def __str__(self):
        return f"${self.net_earning_usd} — {self.bounty.title[:60]}"


class ScanLog(models.Model):
    """Log of scout scan runs."""

    platform = models.CharField(max_length=20, choices=Platform.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    bounties_found = models.IntegerField(default=0)
    bounties_new = models.IntegerField(default=0)
    bounties_updated = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    success = models.BooleanField(default=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Scan: {self.platform} @ {self.started_at:%Y-%m-%d %H:%M} — {self.bounties_found} found"
