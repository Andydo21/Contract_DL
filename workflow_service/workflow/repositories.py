from django.utils import timezone
from .models import Workflow, WorkflowStep, Approval

class WorkflowRepository:
    @staticmethod
    def get_all_workflows():
        """Retrieve all workflows ordered by ID descending."""
        return Workflow.objects.all().order_by("-id").prefetch_related("steps", "steps__approvals")

    @staticmethod
    def get_workflows_by_company(company_id):
        """Retrieve workflows for contract versions belonging to contracts owned by company_id."""
        try:
            from django.db import connections
            db_alias = 'contract_db' if 'contract_db' in connections else 'default'
            with connections[db_alias].cursor() as cursor:
                cursor.execute("""
                    SELECT cv.id 
                    FROM contracts_contractversion cv
                    JOIN contracts_contract c ON cv.contract_id = c.id
                    WHERE c.company_id = %s
                """, [company_id])
                version_ids = [row[0] for row in cursor.fetchall()]
                return Workflow.objects.filter(version_id__in=version_ids).order_by("-id").prefetch_related("steps", "steps__approvals")
        except Exception:
            return Workflow.objects.all().order_by("-id").prefetch_related("steps", "steps__approvals")

    @staticmethod
    def get_contract_info_by_version_ids(version_ids):
        """
        Query database joining contracts_contractversion and contracts_contract
        to retrieve contract title, code, ID, and version_number for given version_ids.
        """
        if not version_ids:
            return {}
        v_ids = list(set(version_ids))
        result_map = {}
        try:
            from django.db import connections
            db_alias = 'contract_db' if 'contract_db' in connections else 'default'
            with connections[db_alias].cursor() as cursor:
                format_strings = ','.join(['%s'] * len(v_ids))
                cursor.execute(f"""
                    SELECT cv.id, c.id, c.title, c.contract_code, cv.version_number
                    FROM contracts_contractversion cv
                    JOIN contracts_contract c ON cv.contract_id = c.id
                    WHERE cv.id IN ({format_strings})
                """, v_ids)
                rows = cursor.fetchall()
                for row in rows:
                    v_id, c_id, title, code, v_num = row
                    result_map[v_id] = {
                        'contract_id': c_id,
                        'contract_title': title,
                        'contract_code': code,
                        'version_number': v_num
                    }
        except Exception:
            pass
        return result_map

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
    def create_step(workflow, step_order, step_name, role_id=None, status="PENDING", description=None):
        """Create a step associated with a workflow."""
        return WorkflowStep.objects.create(
            workflow=workflow,
            step_order=step_order,
            step_name=step_name,
            role_id=role_id,
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

    @staticmethod
    def insert_step(workflow, step_order, step_name, role_id=None, description=None):
        """Insert a step at a specific order, shifting subsequent steps."""
        from django.db import transaction
        from django.db.models import F
        with transaction.atomic():
            WorkflowStep.objects.filter(
                workflow=workflow,
                step_order__gte=step_order
            ).update(step_order=F('step_order') + 1)
            
            new_step = WorkflowStep.objects.create(
                workflow=workflow,
                step_order=step_order,
                step_name=step_name,
                role_id=role_id,
                status="PENDING",
                description=description
            )
            return new_step

    @staticmethod
    def delete_step(step):
        """Delete a step, shifting subsequent steps' order down."""
        from django.db import transaction
        from django.db.models import F
        with transaction.atomic():
            workflow = step.workflow
            order_to_remove = step.step_order
            step.delete()
            
            WorkflowStep.objects.filter(
                workflow=workflow,
                step_order__gt=order_to_remove
            ).update(step_order=F('step_order') - 1)

    @staticmethod
    def update_step_role(step_id, role_id):
        """Update required role ID for a step."""
        step = WorkflowStep.objects.get(id=step_id)
        step.role_id = role_id
        step.save()
        return step

    @staticmethod
    def delete_workflows_by_version(version_id):
        """Delete existing workflows and associated signatures for a contract version."""
        from .models import DigitalSignature
        existing_wfs = Workflow.objects.filter(version_id=version_id)
        for wf in existing_wfs:
            step_ids = list(wf.steps.values_list('id', flat=True))
            DigitalSignature.objects.filter(step_id__in=step_ids).delete()
            wf.delete()
