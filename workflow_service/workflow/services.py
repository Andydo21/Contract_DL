from .repositories import WorkflowRepository
from .rules import recommend_workflow

class WorkflowService:
    def __init__(self):
        self.repo = WorkflowRepository()

    def list_all_workflows(self):
        """Retrieve all workflows ordered by ID descending."""
        return self.repo.get_all_workflows()

    def active_workflow_exists(self, version_id):
        """Check if an active workflow exists for a version."""
        return self.repo.active_workflow_exists(version_id)

    def get_workflow(self, version_id):
        """Retrieve the latest workflow for a version."""
        return self.repo.get_latest_workflow_by_version(version_id)

    def get_workflow_by_id(self, workflow_id):
        """Retrieve a specific workflow by its ID."""
        return self.repo.get_workflow_by_id(workflow_id)

    def create_workflow(self, version_id, workflow_name, contract_text="", clause_types=None, contract_type="", steps_data=None):
        """Build recommendations and create a new workflow."""
        if clause_types is None:
            clause_types = []
        if steps_data is None:
            steps_data = []

        if self.repo.active_workflow_exists(version_id):
            raise ValueError("A workflow is already active for this contract version")

        workflow_type = None
        reasons = None
        recommended_steps = []

        if contract_text or clause_types or contract_type:
            workflow_type, recommended_steps, reasons, ai_workflow_name = recommend_workflow(
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

        # Determine step order
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
                    final_steps.append({
                        "step_order": i + 1,
                        "step_name": step
                    })
        elif steps_data:
            final_steps = steps_data
        else:
            final_steps = [
                {"step_order": 1, "step_name": "Legal Review"},
                {"step_order": 2, "step_name": "Manager Approval"},
                {"step_order": 3, "step_name": "Sign & Archive"},
            ]

        step_role_mapping = {
            "Contract Negotiation": 4, # Legal
            "Legal Review": 4,
            "Technical Review": 7,
            "Security Review": 8,
            "Compliance Review": 9,
            "Finance Review": 6,
            "Procurement Review": 10,
            "Manager Approval": 5,
            "Director Approval": 11,
            "Executive Approval": 11,
            "Contract Signing": 4,
            "Document Archive": 4,
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

    def approve_step(self, step_id, user_id, action, comment=""):
        """Process step approval or rejection and transition the workflow status."""
        step = self.repo.get_step_by_id(step_id)
        if not step:
            raise ValueError("Step not found")

        if action not in ("APPROVED", "REJECTED"):
            raise ValueError("action must be APPROVED or REJECTED")

        # Create approval record
        self.repo.create_approval(
            step=step,
            user_id=user_id,
            action=action,
            comment=comment
        )

        # Update step status
        self.repo.update_step_status(step, action)

        workflow = step.workflow

        if action == "REJECTED":
            self.repo.update_workflow_status(workflow, "REJECTED")
        else:
            if all(s.status == "APPROVED" for s in workflow.steps.all()):
                self.repo.update_workflow_status(workflow, "COMPLETED")
            else:
                self.repo.update_workflow_status(workflow, "IN_PROGRESS")

        return step
