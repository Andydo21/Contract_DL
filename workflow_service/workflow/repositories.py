from django.utils import timezone
from .models import Workflow, WorkflowStep, Approval

class WorkflowRepository:
    @staticmethod
    def get_all_workflows():
        """Retrieve all workflows ordered by ID descending."""
        return Workflow.objects.all().order_by("-id")

    @staticmethod
    def active_workflow_exists(version_id):
        """Check if there is an active workflow (PENDING or IN_PROGRESS) for a contract version."""
        return Workflow.objects.filter(
            version_id=version_id,
            status__in=["PENDING", "IN_PROGRESS"]
        ).exists()

    @staticmethod
    def create_workflow(version_id, workflow_name, workflow_type=None, reasons=None, status="PENDING"):
        """Create a new Workflow record."""
        return Workflow.objects.create(
            version_id=version_id,
            workflow_name=workflow_name,
            status=status,
            workflow_type=workflow_type,
            reasons=reasons,
            started_at=timezone.now()
        )

    @staticmethod
    def create_step(workflow, step_order, step_name, role_id=None,reasons=None, status="PENDING", description=None):
        """Create a step associated with a workflow."""
        return WorkflowStep.objects.create(
            workflow=workflow,
            step_order=step_order,
            step_name=step_name,
            role_id=role_id,
            reason=reason,
            status=status,
            description=description
        )

    @staticmethod
    def get_latest_workflow_by_version(version_id):
        """Retrieve the latest workflow for a contract version."""
        return Workflow.objects.filter(version_id=version_id).order_by("-id").first()

    @staticmethod
    def get_workflow_by_id(workflow_id):
        """Retrieve a specific Workflow by ID."""
        try:
            return Workflow.objects.get(id=workflow_id)
        except Workflow.DoesNotExist:
            return None

    @staticmethod
    def get_step_by_id(step_id):
        """Retrieve a specific WorkflowStep by ID."""
        try:
            return WorkflowStep.objects.get(id=step_id)
        except WorkflowStep.DoesNotExist:
            return None

    @staticmethod
    def create_approval(step, user_id, action, comment=""):
        """Create an Approval record for a step."""
        return Approval.objects.create(
            step=step,
            user_id=user_id,
            status=action,
            comment=comment,
            approved_at=timezone.now()
        )

    @staticmethod
    def update_step_status(step, status):
        """Update a step's status and completed_at timestamp."""
        step.status = status
        step.completed_at = timezone.now()
        step.save()
        return step

    @staticmethod
    def update_workflow_status(workflow, status):
        """Update a workflow's status and completed_at timestamp (if ending)."""
        workflow.status = status
        if status in ("COMPLETED", "REJECTED"):
            workflow.completed_at = timezone.now()
        workflow.save()
        return workflow
