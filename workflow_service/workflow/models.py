from django.db import models

class KeyManagement(models.Model):
    company_id = models.BigIntegerField(verbose_name="Company ID")
    key_alias = models.CharField(max_length=255, verbose_name="Key Alias")
    key_provider = models.CharField(max_length=100, verbose_name="Key Provider")
    key_reference = models.CharField(max_length=512, verbose_name="Key Reference")
    algorithm = models.CharField(max_length=100, verbose_name="Algorithm")
    key_version = models.IntegerField(default=1, verbose_name="Key Version")
    status = models.CharField(max_length=50, default='ACTIVE', verbose_name="Status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    rotated_at = models.DateTimeField(blank=True, null=True, verbose_name="Rotated At")

    class Meta:
        verbose_name = 'Key Management'
        verbose_name_plural = 'Key Managements'

    def __str__(self):
        return f"Key {self.key_alias} (v{self.key_version})"


class Workflow(models.Model):
    version_id = models.BigIntegerField(verbose_name="Contract Version ID")
    workflow_name = models.CharField(max_length=255, verbose_name="Workflow Name")
    status = models.CharField(max_length=50, verbose_name="Status")
    workflow_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="Workflow Type")
    reasons = models.TextField(blank=True, null=True, verbose_name="AI Recommendation Reasons")
    started_at = models.DateTimeField(blank=True, null=True, verbose_name="Started At")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = 'Workflow'
        verbose_name_plural = 'Workflows'

    def __str__(self):
        return self.workflow_name


class WorkflowStep(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='steps', verbose_name="Workflow")
    role_id = models.BigIntegerField(blank=True, null=True, verbose_name="Required Role ID")
    step_order = models.IntegerField(verbose_name="Step Order")
    step_name = models.CharField(max_length=255, verbose_name="Step Name")
    status = models.CharField(max_length=50, verbose_name="Status")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    completed_at = models.DateTimeField(blank=True, null=True, verbose_name="Completed At")

    class Meta:
        verbose_name = 'Workflow Step'
        verbose_name_plural = 'Workflow Steps'

    def __str__(self):
        return f"{self.step_name} (Order: {self.step_order})"


class Approval(models.Model):
    step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name='approvals', verbose_name="Workflow Step")
    user_id = models.BigIntegerField(verbose_name="User ID")
    status = models.CharField(max_length=50, verbose_name="Status")
    comment = models.TextField(blank=True, null=True, verbose_name="Comment")
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name="Approved At")

    class Meta:
        verbose_name = 'Approval'
        verbose_name_plural = 'Approvals'

    def __str__(self):
        return f"Approval for {self.step.step_name} by user {self.user_id}"


class DigitalSignature(models.Model):
    step_id = models.BigIntegerField(verbose_name="Workflow Step ID")
    user_id = models.BigIntegerField(verbose_name="User ID")
    key = models.ForeignKey(KeyManagement, on_delete=models.SET_NULL, null=True, blank=True, related_name='signatures', verbose_name="Signing Key")
    signature_hash = models.CharField(max_length=512, verbose_name="Signature Hash")
    algorithm = models.CharField(max_length=100, default="SHA256withRSA", verbose_name="Signing Algorithm")
    signed_at = models.DateTimeField(auto_now_add=True, verbose_name="Signed At")

    # Blockchain confirmation fields (populated after anchoring to Hyperledger Fabric)
    tx_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Fabric Transaction Hash")
    block_number = models.BigIntegerField(blank=True, null=True, verbose_name="Block Number")
    block_hash = models.CharField(max_length=255, blank=True, null=True, verbose_name="Block Hash")

    # Verification status
    verified = models.BooleanField(default=False, verbose_name="Verified")
    verified_at = models.DateTimeField(blank=True, null=True, verbose_name="Verified At")

    class Meta:
        verbose_name = 'Digital Signature'
        verbose_name_plural = 'Digital Signatures'

    def __str__(self):
        return f"Signature for step {self.step_id} by user {self.user_id}"


class StepDependency(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='dependencies', verbose_name="Workflow")
    prerequisite_step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name='prerequisites_for', verbose_name="Prerequisite Step (Nối đến - Phải xong trước)")
    dependent_step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name='dependent_on', verbose_name="Dependent Step (Bị nối - Bị khóa)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = 'Step Dependency'
        verbose_name_plural = 'Step Dependencies'
        unique_together = ('prerequisite_step', 'dependent_step')

    def __str__(self):
        return f"{self.prerequisite_step.step_name} -> {self.dependent_step.step_name}"


