from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('EXPERT', 'Expert'),
        ('VIEWER', 'Viewer'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='VIEWER')

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'


class Contract(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ANALYZING', 'Analyzing'),
        ('ANALYZED', 'Analyzed'),
        ('APPROVED', 'Approved'),
    )
    contract_code = models.CharField(max_length=50, unique=True, verbose_name="Contract Code")
    title = models.CharField(max_length=255, verbose_name="Title")
    contract_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="Contract Type")
    start_date = models.DateField(blank=True, null=True, verbose_name="Start Date")
    end_date = models.DateField(blank=True, null=True, verbose_name="End Date")
    contract_value = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, verbose_name="Contract Value")
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='DRAFT', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'

    def __str__(self):
        return f"{self.contract_code} - {self.title}"


class ContractFile(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='files', verbose_name="Contract")
    file_path = models.CharField(max_length=512, verbose_name="File Path")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Uploaded At")

    class Meta:
        verbose_name = 'Contract File'
        verbose_name_plural = 'Contract Files'

    def __str__(self):
        return f"File for {self.contract.contract_code} ({self.uploaded_at})"


class Clause(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='clauses', verbose_name="Contract")
    clause_title = models.CharField(max_length=255, verbose_name="Clause Title")
    clause_content = models.TextField(verbose_name="Clause Content")

    class Meta:
        verbose_name = 'Clause'
        verbose_name_plural = 'Clauses'

    def __str__(self):
        return f"{self.clause_title} ({self.contract.contract_code})"


class Risk(models.Model):
    SEVERITY_CHOICES = (
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    )
    risk_name = models.CharField(max_length=255, unique=True, verbose_name="Risk Name")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    severity_level = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='MEDIUM', verbose_name="Severity Level")

    class Meta:
        verbose_name = 'Risk Definition'
        verbose_name_plural = 'Risk Definitions'

    def __str__(self):
        return f"{self.risk_name} ({self.severity_level})"


class AIAnalysis(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='ai_analyses', verbose_name="Contract")
    model_name = models.CharField(max_length=100, verbose_name="Model Name")
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Overall Score")
    summary = models.TextField(blank=True, null=True, verbose_name="Summary")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Analyzed At")

    class Meta:
        verbose_name = 'AI Analysis'
        verbose_name_plural = 'AI Analyses'

    def __str__(self):
        return f"Analysis ({self.model_name}) - {self.contract.contract_code} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class RiskFinding(models.Model):
    RISK_LEVEL_CHOICES = (
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    )
    analysis = models.ForeignKey(AIAnalysis, on_delete=models.CASCADE, related_name='findings', verbose_name="AI Analysis")
    clause = models.ForeignKey(Clause, on_delete=models.SET_NULL, null=True, blank=True, related_name='findings', verbose_name="Associated Clause")
    risk = models.ForeignKey(Risk, on_delete=models.PROTECT, related_name='findings', verbose_name="Risk Category")
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default='MEDIUM', verbose_name="Risk Level")
    explanation = models.TextField(verbose_name="Explanation")
    recommendation = models.TextField(blank=True, null=True, verbose_name="Recommendation")

    class Meta:
        verbose_name = 'Risk Finding'
        verbose_name_plural = 'Risk Findings'

    def __str__(self):
        return f"Finding: {self.risk.risk_name} ({self.risk_level})"


class Review(models.Model):
    RISK_LEVEL_CHOICES = (
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    )
    analysis = models.ForeignKey(AIAnalysis, on_delete=models.CASCADE, related_name='reviews', verbose_name="AI Analysis")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews', verbose_name="Reviewer")
    comment = models.TextField(verbose_name="Comment")
    final_risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, verbose_name="Final Risk Level")
    reviewed_at = models.DateTimeField(auto_now_add=True, verbose_name="Reviewed At")

    class Meta:
        verbose_name = 'Expert Review'
        verbose_name_plural = 'Expert Reviews'

    def __str__(self):
        return f"Review by {self.user.username} on {self.analysis.contract.contract_code}"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs', verbose_name="User")
    action = models.CharField(max_length=100, verbose_name="Action")
    target_model = models.CharField(max_length=100, verbose_name="Target Model")
    target_id = models.BigIntegerField(verbose_name="Target ID")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Timestamp")

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        username = self.user.username if self.user else "System"
        return f"{username} - {self.action} on {self.target_model} (ID: {self.target_id})"
