from django.utils import timezone
from .repositories import WorkflowRepository, KeyManagementRepository
from .rules import recommend_workflow


def _step_to_dict(st):
    approvals_list = []
    approvals = WorkflowRepository.step_approvals(st)
    for app in approvals:
        approvals_list.append({
            "user_id": app.user_id,
            "status": app.status,
            "comment": app.comment,
            "approved_at": app.approved_at.isoformat() if app.approved_at else None,
        })
    comment = None
    if approvals:
        comment = approvals[-1].comment

    prereqs = []
    if hasattr(st, 'dependent_on'):
        for dep in WorkflowRepository.step_prerequisites(st):
            prereqs.append({
                "dep_id": dep.id,
                "prereq_step_id": dep.prerequisite_step_id,
                "prereq_step_name": dep.prerequisite_step.step_name,
                "prereq_step_order": dep.prerequisite_step.step_order,
                "prereq_step_status": dep.prerequisite_step.status,
                "is_blocking": dep.prerequisite_step.status != "APPROVED"
            })

    return {
        "id": st.id, "step_order": st.step_order, "step_name": st.step_name,
        "role_id": st.role_id, "status": st.status,
        "completed_at": st.completed_at.isoformat() if st.completed_at else None,
        "comment": comment,
        "approvals": approvals_list,
        "prerequisites": prereqs,
    }


class WorkflowService:
    def __init__(self):
        self.repo = WorkflowRepository()

    def list_workflows_for_user(self, user):
        """Every workflow for a superuser, the workflows of the user's company otherwise; nothing for a request whose
        user or company is unknown (the tenant guard should never let one through, this is the safe default)."""
        if not user or not getattr(user, 'is_authenticated', False):
            return []
        if getattr(user, 'is_superuser', False):
            return self.repo.get_all_workflows()
        company_id = getattr(user, 'company_id', None)
        return self.repo.get_workflows_by_company(company_id) if company_id else []

    def active_workflow_exists(self, version_id):
        return self.repo.active_workflow_exists(version_id)

    def get_workflow(self, version_id):
        return self.repo.get_latest_workflow_by_version(version_id)

    def get_workflow_by_id(self, workflow_id):
        return self.repo.get_workflow_by_id(workflow_id)

    def _serialize_workflow(self, wf, contract_info=None):
        if not wf:
            return None
        c_info = contract_info or {}
        steps = [_step_to_dict(st) for st in sorted(self.repo.workflow_steps(wf), key=lambda s: s.step_order)]
        
        deps = self.repo.workflow_dependencies(wf)
        serialized_deps = [
            {
                "id": dep.id,
                "prerequisite_step_id": dep.prerequisite_step_id,
                "prerequisite_step_name": dep.prerequisite_step.step_name,
                "prerequisite_step_order": dep.prerequisite_step.step_order,
                "prerequisite_step_status": dep.prerequisite_step.status,
                "dependent_step_id": dep.dependent_step_id,
                "dependent_step_name": dep.dependent_step.step_name,
                "dependent_step_order": dep.dependent_step.step_order,
                "dependent_step_status": dep.dependent_step.status,
                "is_blocking": dep.prerequisite_step.status != "APPROVED"
            }
            for dep in deps
        ]

        return {
            "workflow_id":   wf.id,
            "version_id":    wf.version_id,
            "contract_id":   c_info.get('contract_id'),
            "contract_title": c_info.get('contract_title', ''),
            "contract_code": c_info.get('contract_code', ''),
            "version_number": c_info.get('version_number', 1),
            "workflow_name": wf.workflow_name,
            "status":        wf.status,
            "workflow_type": wf.workflow_type,
            "reasons":       wf.reasons,
            "started_at":    wf.started_at.isoformat() if wf.started_at else None,
            "completed_at":  wf.completed_at.isoformat() if wf.completed_at else None,
            "steps":         steps,
            "dependencies":  serialized_deps,
        }

    def get_workflow_detail_dict(self, workflow_id):
        wf = self.repo.get_workflow_by_id(workflow_id)
        if not wf:
            return None
        info_map = self.repo.get_contract_info_by_version_ids([wf.version_id])
        return self._serialize_workflow(wf, info_map.get(wf.version_id))

    def list_workflows_with_contract_info_for_user(self, user):
        workflows = self.list_workflows_for_user(user)
        version_ids = [wf.version_id for wf in workflows]
        info_map = self.repo.get_contract_info_by_version_ids(version_ids)
        return [self._serialize_workflow(wf, info_map.get(wf.version_id)) for wf in workflows]

    def get_workflow_dict_by_version(self, version_id):
        wf = self.get_workflow(version_id)
        if not wf:
            return None
        info_map = self.repo.get_contract_info_by_version_ids([wf.version_id])
        return self._serialize_workflow(wf, info_map.get(wf.version_id))

    def create_workflow(self, version_id, workflow_name, contract_text="", clause_types=None, contract_type="", steps_data=None):
        if clause_types is None:
            clause_types = []
        if steps_data is None:
            steps_data = []

        # Clear existing workflow and its signatures if it exists
        self.repo.delete_workflows_by_version(version_id)

        workflow_type = None
        reasons = None
        recommended_steps = []

        if contract_text or clause_types or contract_type:
            workflow_type, recommended_steps, reasons, ai_workflow_name = recommend_workflow(
                contract_text, clause_types, contract_type
            )
            if not workflow_name or workflow_name == "Contract Approval Workflow":
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

        return workflow

    def insert_step(self, workflow_id, step_order, step_name, role_id=None, description=None):
        """Insert a step at a specific order, shifting subsequent steps."""
        workflow = self.repo.get_workflow_by_id(workflow_id)
        if not workflow:
            raise ValueError("Workflow not found")
        if workflow.status in ("COMPLETED", "REJECTED"):
            raise ValueError("Cannot insert step into a completed or rejected workflow")

        return self.repo.insert_step(
            workflow=workflow,
            step_order=step_order,
            step_name=step_name,
            role_id=role_id,
            description=description
        )

    def delete_step(self, step_id):
        """Delete a step by ID and shift orders of remaining steps."""
        step = self.repo.get_step_by_id(step_id)
        if not step:
            raise ValueError("Step not found")
        
        workflow = step.workflow
        if workflow.status in ("COMPLETED", "REJECTED"):
            raise ValueError("Cannot delete step from a completed or rejected workflow")
            
        if step.requires_signature:
            raise ValueError('Mandatory signing steps cannot be deleted')
        self.repo.delete_step(step)

    def delete_workflows_for_version(self, version_id):
        """Remove every workflow of a contract version with its steps, approvals, dependencies and signatures
        (the contract itself is being deleted)."""
        count = self.repo.count_workflows_by_version(version_id)
        self.repo.delete_workflows_by_version(version_id)
        return count

    def update_step_role(self, step_id, role_id):
        """Update required role ID for a step via repository."""
        return self.repo.update_step_role(step_id, role_id)

    def approve_step(self, step_id, user_id, action, comment="", company_id=None, is_manager=False):
        """Approve reviews; signing steps advance only through verified ledger operations."""
        from django.db import transaction

        step = self.repo.get_step_by_id(step_id)
        if not step:
            raise ValueError("Step not found")

        if action not in ("APPROVED", "REJECTED", "FORCE_COMPLETE"):
            raise ValueError("action must be APPROVED, REJECTED, or FORCE_COMPLETE")

        # Custom Step Dependency Check: Block approval if prerequisite steps are not APPROVED
        if action in ("APPROVED", "FORCE_COMPLETE"):
            unmet_deps = self.repo.unmet_dependencies(step)
            if unmet_deps:
                unmet_names = ", ".join([f"'{d.prerequisite_step.step_name}'" for d in unmet_deps])
                raise ValueError(f"Không thể ký/duyệt bước '{step.step_name}' vì đang bị khóa bởi đường nối phụ thuộc: Bước {unmet_names} chưa hoàn thành.")

        signing_step = step.requires_signature
        if signing_step and action in ('APPROVED', 'FORCE_COMPLETE'):
            raise ValueError('Use /contract-ledger/ to sign the exact version with an approved RSA key and Step ID.')
        if action == 'FORCE_COMPLETE' and not is_manager:
            raise ValueError('Manager permission required for FORCE_COMPLETE')

        if action == "FORCE_COMPLETE":
            with transaction.atomic():
                self.repo.create_approval(step=step, user_id=user_id, action="APPROVED", comment=comment or "Accepted & Completed by Manager")
                self.repo.update_step_status(step, "APPROVED")

                workflow = step.workflow
                if self.repo.workflow_fully_approved(workflow):
                    self.repo.update_workflow_status(workflow, "COMPLETED")
                else:
                    self.repo.update_workflow_status(workflow, "IN_PROGRESS")
            return step

        # Review approval is separate from a cryptographic contract signature.
        with transaction.atomic():
            self.repo.create_approval(step=step, user_id=user_id, action=action, comment=comment)
            self.repo.update_step_status(step, action)
            workflow = step.workflow
            if action == 'REJECTED':
                self.repo.update_workflow_status(workflow, 'REJECTED')
            else:
                complete = self.repo.workflow_fully_approved(workflow)
                self.repo.update_workflow_status(workflow, 'COMPLETED' if complete else 'IN_PROGRESS')
        return step

    def add_dependency(self, workflow_id, prerequisite_step_id, dependent_step_id):
        if int(prerequisite_step_id) == int(dependent_step_id):
            raise ValueError("Một bước không thể nối phụ thuộc tới chính nó.")
        
        prereq = self.repo.get_step_by_id(prerequisite_step_id)
        dependent = self.repo.get_step_by_id(dependent_step_id)
        if not prereq or not dependent:
            raise ValueError("Không tìm thấy các bước để tạo đường nối.")
        
        if prereq.workflow_id != int(workflow_id) or dependent.workflow_id != int(workflow_id):
            raise ValueError("Các bước không thuộc cùng một quy trình (Workflow).")

        if self._reaches(prereq.workflow, dependent.id, prereq.id):
            raise ValueError("Không thể tạo đường nối vòng lặp phụ thuộc giữa các bước.")

        return self.repo.get_or_create_dependency(workflow_id, prereq, dependent)

    def _reaches(self, workflow, start_id, target_id):
        """Whether target_id already waits, directly or through other steps, on start_id. Linking target before start
        would then close a cycle, and every step on it would stay locked for ever."""
        follows = {}
        for dep in self.repo.workflow_dependencies(workflow):
            follows.setdefault(dep.prerequisite_step_id, []).append(dep.dependent_step_id)
        seen, todo = set(), [start_id]
        while todo:
            step = todo.pop()
            if step == target_id:
                return True
            if step not in seen:
                seen.add(step)
                todo.extend(follows.get(step, []))
        return False

    def delete_dependency(self, dependency_id):
        dep = self.repo.get_dependency_by_id(dependency_id)
        if not dep:
            raise ValueError("Không tìm thấy đường nối phụ thuộc này.")
        self.repo.delete(dep)


class KeyManagementService:
    """Service for cryptographic key lifecycle and digital signature management."""

    @staticmethod
    def list_keys(company_id=None):
        return KeyManagementRepository.list_keys(company_id)

    @staticmethod
    def get_key(key_id):
        return KeyManagementRepository.get_key(key_id)

    @staticmethod
    def create_key(company_id, key_alias, key_provider, key_reference, algorithm):
        return KeyManagementRepository.create_key(
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
        old_key = KeyManagementRepository.get_key(key_id)
        if old_key.status == 'REVOKED':
            raise ValueError("Cannot rotate a revoked key")
        old_key.status = 'ROTATED'
        old_key.rotated_at = timezone.now()
        KeyManagementRepository.save(old_key)
        return KeyManagementRepository.create_key(
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
        key = KeyManagementRepository.get_key(key_id)
        key.status = 'REVOKED'
        key.rotated_at = timezone.now()
        return KeyManagementRepository.save(key)

    @staticmethod
    def get_active_key(company_id):
        return KeyManagementRepository.active_key(company_id)

    @staticmethod
    def list_signatures(step_id=None, user_id=None):
        return KeyManagementRepository.list_signatures(step_id, user_id)
