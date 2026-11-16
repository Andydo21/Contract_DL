from django.utils import timezone
from .models import Workflow, WorkflowStep, Approval, StepDependency, KeyManagement, DigitalSignature

class WorkflowRepository:
    @staticmethod
    def ping_databases():
        from django.db import connections
        for alias in ['default', 'contract_db']:
            with connections[alias].cursor() as cursor:
                cursor.execute('SELECT 1')

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
            return Workflow.objects.none()

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
        import re
        return WorkflowStep.objects.create(
            workflow=workflow,
            step_order=step_order,
            step_name=step_name,
            role_id=role_id,
            status=status,
            description=description,
            requires_signature=bool(re.search(r'ký kết|chữ ký|\bsign(?:ing)?\b', step_name, re.I))
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

    # ------------------------------------------------------------------ reads used by serialization
    @staticmethod
    def step_approvals(step):
        return list(step.approvals.all().order_by('id'))

    @staticmethod
    def step_prerequisites(step):
        return list(step.dependent_on.select_related('prerequisite_step').all())

    @staticmethod
    def workflow_steps(workflow):
        return list(workflow.steps.all())

    @staticmethod
    def workflow_dependencies(workflow):
        return list(workflow.dependencies.select_related('prerequisite_step', 'dependent_step').all())

    @staticmethod
    def workflow_fully_approved(workflow):
        return not workflow.steps.exclude(status='APPROVED').exists()

    @staticmethod
    def count_workflows_by_version(version_id):
        return Workflow.objects.filter(version_id=version_id).count()

    # ------------------------------------------------------------------ step dependencies
    @staticmethod
    def unmet_dependencies(step):
        return list(StepDependency.objects.filter(dependent_step=step).exclude(prerequisite_step__status='APPROVED')
                    .select_related('prerequisite_step'))

    @staticmethod
    def get_or_create_dependency(workflow_id, prerequisite_step, dependent_step):
        dep, _ = StepDependency.objects.get_or_create(workflow_id=workflow_id, prerequisite_step=prerequisite_step,
                                                      dependent_step=dependent_step)
        return dep

    @staticmethod
    def get_dependency_by_id(dependency_id):
        return StepDependency.objects.filter(id=dependency_id).first()

    @staticmethod
    def delete(obj):
        obj.delete()


class KeyManagementRepository:
    @staticmethod
    def list_keys(company_id=None):
        qs = KeyManagement.objects.all().order_by('-created_at')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return list(qs)

    @staticmethod
    def get_key(key_id):
        return KeyManagement.objects.get(id=key_id)

    @staticmethod
    def create_key(**fields):
        return KeyManagement.objects.create(**fields)

    @staticmethod
    def active_key(company_id=None):
        qs = KeyManagement.objects.filter(status='ACTIVE')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs.order_by('-key_version').first()

    @staticmethod
    def save(key):
        key.save()
        return key

    @staticmethod
    def create_signature(**fields):
        return DigitalSignature.objects.create(**fields)

    @staticmethod
    def list_signatures(step_id=None, user_id=None):
        qs = DigitalSignature.objects.select_related('key').order_by('-signed_at')
        if step_id:
            qs = qs.filter(step_id=step_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return list(qs)


class TenantLookupRepository:
    """Ownership lookups used by the tenant guard."""

    @staticmethod
    def step(step_id):
        return WorkflowStep.objects.get(pk=step_id)

    @staticmethod
    def dependency_workflow_id(dependency_id):
        return StepDependency.objects.get(pk=dependency_id).workflow_id

    @staticmethod
    def workflow_version_id(workflow_id):
        return Workflow.objects.get(pk=workflow_id).version_id

    @staticmethod
    def key_company_id(key_id):
        return KeyManagement.objects.get(pk=key_id).company_id

    @staticmethod
    def actor(user_id):
        """(id, company_id, is_active, is_superuser, role_name, role_id) of a contract-web user."""
        from django.db import connections
        with connections['contract_db'].cursor() as c:
            c.execute('SELECT u.id,u.company_id,u.is_active,u.is_superuser,r.role_name,u.role_id FROM contracts_user u '
                      'LEFT JOIN contracts_role r ON r.id=u.role_id WHERE u.id=%s', [user_id])
            return c.fetchone()

    @staticmethod
    def version_company(version_id):
        from django.db import connections
        with connections['contract_db'].cursor() as c:
            c.execute('SELECT c.company_id FROM contracts_contractversion v JOIN contracts_contract c ON c.id=v.contract_id '
                      'WHERE v.id=%s', [version_id])
            return c.fetchone()
