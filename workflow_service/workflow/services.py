import hashlib
import os
import uuid
from django.utils import timezone
from .repositories import WorkflowRepository
from .rules import recommend_workflow


class WorkflowService:
    def __init__(self):
        self.repo = WorkflowRepository()

    def list_all_workflows(self):
        """Retrieve all workflows ordered by ID descending."""
        return self.repo.get_all_workflows()

    def active_workflow_exists(self, version_id):
        return self.repo.active_workflow_exists(version_id)

    def get_workflow(self, version_id):
        return self.repo.get_latest_workflow_by_version(version_id)

    def get_workflow_by_id(self, workflow_id):
        return self.repo.get_workflow_by_id(workflow_id)

    def create_workflow(self, version_id, workflow_name, contract_text="", clause_types=None, contract_type="", steps_data=None):
        if clause_types is None:
            clause_types = []
        if steps_data is None:
            steps_data = []

        if self.repo.active_workflow_exists(version_id):
            raise ValueError("A workflow is already active for this contract version")

        workflow_type = None
        reasons = None
        recommended_steps = []
        confidence = 0.0

        if contract_text or clause_types or contract_type:
            workflow_type, recommended_steps, reasons, ai_workflow_name, confidence = recommend_workflow(
                contract_text, clause_types, contract_type
            )
            if ai_workflow_name:
                workflow_name = ai_workflow_name

        workflow = self.repo.create_workflow(
            version_id=version_id,
            workflow_name=workflow_name,
            workflow_type=workflow_type,
            reasons=reasons
        )

        if recommended_steps:
            final_steps = []
            for i, step in enumerate(recommended_steps):
                if isinstance(step, dict):
                    final_steps.append({
                        "step_order": i + 1,
                        "step_name": step.get("step_name"),
                        "role_id": step.get("role_id"),
                        "description": step.get("description", "")
                    })
                else:
                    final_steps.append({"step_order": i + 1, "step_name": step})
        elif steps_data:
            final_steps = steps_data
        else:
            final_steps = [
                {"step_order": 1, "step_name": "Legal Review"},
                {"step_order": 2, "step_name": "Manager Approval"},
                {"step_order": 3, "step_name": "Sign & Archive"},
            ]

        step_role_mapping = {
            "Contract Negotiation": 4, "Legal Review": 4,
            "Technical Review": 7, "Security Review": 8,
            "Compliance Review": 9, "Finance Review": 6,
            "Procurement Review": 10, "Manager Approval": 5,
            "Director Approval": 11, "Executive Approval": 11,
            "Contract Signing": 4, "Document Archive": 4,
        }

        for s in final_steps:
            name = s.get("step_name", "Review")
            r_id = s.get("role_id") or step_role_mapping.get(name)
            desc = s.get("description")
            self.repo.create_step(
                workflow=workflow,
                step_order=s.get("step_order", 1),
                step_name=name,
                role_id=r_id,
                description=desc,
            )

        workflow.confidence = confidence
        return workflow

    def approve_step(self, step_id, user_id, action, comment="", company_id=None):
        """Process step approval/rejection. Auto-creates DigitalSignature on APPROVED."""
        from django.db import transaction

        step = self.repo.get_step_by_id(step_id)
        if not step:
            raise ValueError("Step not found")

        if action not in ("APPROVED", "REJECTED"):
            raise ValueError("action must be APPROVED or REJECTED")

        # Perform blockchain verification BEFORE modifying database if APPROVED
        sig_hash = None
        if action == "APPROVED":
            sig_hash = hashlib.sha256(
                f"{step_id}:{user_id}:{uuid.uuid4()}:{timezone.now().isoformat()}".encode()
            ).hexdigest()
            skip_blockchain = os.environ.get("WORKFLOW_SKIP_BLOCKCHAIN", "").lower() in ("1", "true", "yes")
            if not skip_blockchain:
                try:
                    import requests
                    blockchain_service_url = os.environ.get("BLOCKCHAIN_SERVICE_URL", "http://localhost:8002")

                    cert_resp = requests.get(f"{blockchain_service_url}/certificate/{user_id}/", timeout=5)
                    if cert_resp.status_code != 200:
                        raise ValueError(f"Could not retrieve certificate for user {user_id} from blockchain service")
                    certs = cert_resp.json().get("certificates", [])
                    active_certs = [c for c in certs if c.get("status") == "ACTIVE" and not c.get("revoked")]
                    if not active_certs:
                        raise ValueError(f"User {user_id} has no active/valid signature certificate on the Blockchain Service")
                    cert_id = active_certs[0]["certificate_id"]

                    sign_resp = requests.post(f"{blockchain_service_url}/sign/", json={
                        "step_id": step_id,
                        "user_id": user_id,
                        "certificate_id": cert_id,
                        "signature_hash": sig_hash
                    }, timeout=15)

                    if sign_resp.status_code != 200:
                        error_msg = sign_resp.json().get("error", "Unknown error during anchoring")
                        raise ValueError(f"Blockchain signature verification/anchoring failed: {error_msg}")

                except requests.RequestException as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Blockchain service unavailable (%s); approving with local signature only.", exc
                    )
                except ValueError:
                    raise

        with transaction.atomic():
            self.repo.create_approval(step=step, user_id=user_id, action=action, comment=comment)
            self.repo.update_step_status(step, action)

            if action == "APPROVED" and sig_hash:
                # 3. Save locally in workflow DB
                KeyManagementService.create_signature_for_step(
                    step_id=step_id,
                    user_id=user_id,
                    company_id=company_id,
                    signature_hash=sig_hash
                )

            workflow = step.workflow
            if action == "REJECTED":
                self.repo.update_workflow_status(workflow, "REJECTED")
            else:
                if all(s.status == "APPROVED" for s in workflow.steps.all()):
                    self.repo.update_workflow_status(workflow, "COMPLETED")
                else:
                    self.repo.update_workflow_status(workflow, "IN_PROGRESS")

        return step


class KeyManagementService:
    """Service for cryptographic key lifecycle and digital signature management."""

    @staticmethod
    def list_keys(company_id=None):
        from .models import KeyManagement
        qs = KeyManagement.objects.all().order_by('-created_at')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return list(qs)

    @staticmethod
    def get_key(key_id):
        from .models import KeyManagement
        return KeyManagement.objects.get(id=key_id)

    @staticmethod
    def create_key(company_id, key_alias, key_provider, key_reference, algorithm):
        from .models import KeyManagement
        return KeyManagement.objects.create(
            company_id=company_id,
            key_alias=key_alias,
            key_provider=key_provider,
            key_reference=key_reference,
            algorithm=algorithm,
            key_version=1,
            status='ACTIVE'
        )

    @staticmethod
    def rotate_key(key_id):
        """Deactivate old key, create new version with incremented key_version."""
        from .models import KeyManagement
        old_key = KeyManagement.objects.get(id=key_id)
        if old_key.status == 'REVOKED':
            raise ValueError("Cannot rotate a revoked key")
        old_key.status = 'ROTATED'
        old_key.rotated_at = timezone.now()
        old_key.save()
        return KeyManagement.objects.create(
            company_id=old_key.company_id,
            key_alias=old_key.key_alias,
            key_provider=old_key.key_provider,
            key_reference=old_key.key_reference,
            algorithm=old_key.algorithm,
            key_version=old_key.key_version + 1,
            status='ACTIVE'
        )

    @staticmethod
    def revoke_key(key_id):
        from .models import KeyManagement
        key = KeyManagement.objects.get(id=key_id)
        key.status = 'REVOKED'
        key.rotated_at = timezone.now()
        key.save()
        return key

    @staticmethod
    def get_active_key(company_id):
        from .models import KeyManagement
        return KeyManagement.objects.filter(
            company_id=company_id, status='ACTIVE'
        ).order_by('-key_version').first()

    @staticmethod
    def create_signature_for_step(step_id, user_id, signature_hash, company_id=None):
        from .models import DigitalSignature, KeyManagement
        key = None
        if company_id:
            key = KeyManagement.objects.filter(
                company_id=company_id, status='ACTIVE'
            ).order_by('-key_version').first()
        if not key:
            # Fallback: use any active key in the system
            key = KeyManagement.objects.filter(status='ACTIVE').order_by('-key_version').first()
        return DigitalSignature.objects.create(
            step_id=step_id,
            user_id=user_id,
            key=key,
            signature_hash=signature_hash,
        )

    @staticmethod
    def list_signatures(step_id=None, user_id=None):
        from .models import DigitalSignature
        qs = DigitalSignature.objects.select_related('key').order_by('-signed_at')
        if step_id:
            qs = qs.filter(step_id=step_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return list(qs)
