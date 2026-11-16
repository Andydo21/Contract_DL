from contract.approvals.repositories import workflow_data_repository as data_repository
from contract.contracts.repositories.contract_repository import ContractRepository
from contract.core.repositories.audit_log_repository import AuditLogRepository

def _service_headers():
    """The workflow tenant guard accepts the system identity only with its shared token."""
    from django.conf import settings
    from shared.jwt_middleware import get_system_auth_header
    return {**get_system_auth_header(), 'X-Workflow-Service-Token': settings.WORKFLOW_SERVICE_TOKEN}


class WorkflowService:

    def __init__(self):
        self.contract_repo = ContractRepository()
        self.audit_repo = AuditLogRepository()

    @staticmethod
    def _version(contract, version_id):
        """The requested version of the contract, or its latest one (None when it has none)."""
        from contract.contracts.models import ContractVersion
        if not version_id:
            return contract.latest_version
        try:
            return data_repository.get_versions_for_push_to_workflow(contract, version_id)
        except ContractVersion.DoesNotExist:
            raise ValueError('Version not found.')

    def push_to_workflow(self, contract_id, version_id=None):
        """Đẩy contract lên workflow-service để tạo quy trình phê duyệt."""
        import requests
        from django.conf import settings
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        version = self._version(contract, version_id)
        if not version:
            raise ValueError('Contract has no version to push.')
        # The text the workflow rules read: the stored raw text, else the document's own text (a PDF's text layer,
        # never its bytes), else the extracted clauses.
        from contract.core.services.stored_file_service import document_text
        raw_content = '\n\n'.join(ctx.content for ctx in data_repository.order_by_contexts_for_push_to_workflow(version))
        if not raw_content:
            raw_content = document_text(data_repository.first_files_for_push_to_workflow(version))
        if not raw_content:
            clauses = list(data_repository.all_ai_extract_clauses_for_push_to_workflow(version))
            if clauses:
                raw_content = '\n\n'.join([f'--- {cl.clause_title} ---\n{cl.clause_content}' for cl in clauses])
        clause_types = list(data_repository.distinct_ai_extract_clauses_for_push_to_workflow(version))
        workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')
        payload = {'version_id': version.id, 'workflow_name': f'Approval Workflow – {contract.title}', 'contract_text': raw_content, 'clause_types': clause_types, 'contract_type': contract.contract_type or ''}
        try:
            resp = requests.post(f'{workflow_url}/workflows/', json=payload, headers=_service_headers(), timeout=300)
            if resp.status_code == 409:
                get_resp = requests.get(f'{workflow_url}/workflows/{version.id}/', headers=_service_headers(), timeout=300)
                get_resp.raise_for_status()
                result = get_resp.json()
            else:
                resp.raise_for_status()
                result = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f'Workflow service error: {e}')
        # The service wraps a created workflow as {"success": true, "workflow": {...}}; a GET returns it bare.
        result = result.get('workflow', result) if isinstance(result, dict) else {}
        admin_user = data_repository.first_user_for_push_to_workflow()
        self.audit_repo.log_action(admin_user, 'PUSHED_TO_WORKFLOW', 'Contract', contract.id)
        return {'contract_id': contract.id, 'workflow_id': result.get('workflow_id'), 'workflow_name': result.get('workflow_name'), 'status': result.get('status'), 'steps': result.get('steps', [])}

    def delete_workflows(self, version_ids):
        """Delete the approval workflows of these contract versions in workflow-service (the contract is being
        deleted). Returns how many were removed; raises RuntimeError when the service cannot do it."""
        import requests
        from django.conf import settings
        workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')
        deleted = 0
        for version_id in version_ids:
            try:
                resp = requests.post(f'{workflow_url}/workflows/versions/{version_id}/delete/', headers=_service_headers(), timeout=10)
                resp.raise_for_status()
                deleted += resp.json().get('deleted', 0)
            except (requests.RequestException, ValueError) as e:
                raise RuntimeError(f'Workflow service error: {e}')
        return deleted

    def get_workflow_status(self, contract_id, version_id=None):
        """Lấy trạng thái workflow từ workflow-service."""
        import requests
        from django.conf import settings
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        version = self._version(contract, version_id)
        if not version:
            return None
        workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')
        try:
            resp = requests.get(f'{workflow_url}/workflows/{version.id}/', headers=_service_headers(), timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f'Workflow service error: {e}')
