from ai.analysis.repositories import analysis_data_repository as data_repository
from contract.contracts.services.contract_service import ContractService
from ai.analysis.services.analysis_history_service import AnalysisHistoryService
from contract.core.services.results import ServiceResult
from contract.core.services.access_service import check_contract_permission as _check_contract_permission
contract_service = ContractService()
analysis_history_service = AnalysisHistoryService()

def analyze_contract(contract_id, user, method, data, form, query):
    """
    POST: Queue the risk analysis of the contract's latest version as a background job.
    """
    if method == 'POST':
        from contract.contracts.models import Contract
        try:
            contract_obj = data_repository.get_contract_for_analyze_contract(contract_id)
            if not _check_contract_permission(user, contract_obj):
                return ServiceResult({'error': 'Permission Denied.'}, status=403)
            # Clause-by-clause analysis takes minutes: it runs as a background job the page follows.
            from ai.ai_extract.services import bulk_service
            from ai.ai_extract.repositories import layout_repository
            if layout_repository.latest_run(contract_obj.latest_version, completed=True) is None:
                return ServiceResult({'error': 'Hợp đồng chưa trích xuất xong; hãy chờ trích xuất hoàn tất rồi phân tích rủi ro.'}, status=409)
            job = bulk_service.start(user, [int(contract_id)], 'risk')
            return ServiceResult({'success': True, 'contract_id': contract_obj.id, 'job_id': job['id'], 'job_status': job['status']}, status=202)
        except Contract.DoesNotExist:
            return ServiceResult({'error': 'Contract not found.'}, status=404)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def submit_review(analysis_id, method, data, user=None):
    """
    POST: Submit legal expert review.
    """
    if method == 'POST':
        comment = data.get('comment', '')
        final_risk_level = data.get('final_risk_level', 'MEDIUM')
        if not comment:
            return ServiceResult({'error': 'Comment is required.'}, status=400)
        try:
            analysis = contract_service.analysis_repo.get_analysis_by_id(analysis_id)
            if analysis is None:
                return ServiceResult({'error': 'Analysis not found.'}, status=404)
            if user is None or not _check_contract_permission(user, analysis.version.contract):
                return ServiceResult({'error': 'Permission Denied.'}, status=403)
            review = contract_service.submit_expert_review(analysis_id=analysis_id, comment=comment, final_risk_level=final_risk_level, user=user)
            return ServiceResult({'success': True, 'review_id': review.id, 'status': review.analysis.version.contract.status})
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def analyses_list(user, method, data):
    """
    GET: Return full list of all AI analyses ordered by most recent.
    """
    if method == 'GET':
        try:
            company = None if user.is_superuser else user.company
            data = analysis_history_service.list_all_analyses(company=company)
            return ServiceResult(data)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=500)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

