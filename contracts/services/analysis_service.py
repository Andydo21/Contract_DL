from contracts.repositories import analysis_data_repository as data_repository
from contracts.services import ContractService, AnalysisHistoryService
from contracts.services.results import ServiceResult
from contracts.services.access_service import check_contract_permission as _check_contract_permission
contract_service = ContractService()
analysis_history_service = AnalysisHistoryService()

def analyze_contract(contract_id, user, method, data, form, query):
    """
    POST: Run the AI analysis simulator for the given contract.
    """
    if method == 'POST':
        version_id = query.get('version_id') or form.get('version_id')
        if not version_id and data:
            try:
                body = data
                version_id = body.get('version_id')
            except Exception:
                pass
        try:
            contract_obj = data_repository.get_contract_for_analyze_contract(contract_id)
            if not _check_contract_permission(user, contract_obj):
                return ServiceResult({'error': 'Permission Denied.'}, status=403)
            # Clause-by-clause analysis takes minutes: it runs as a background job the page follows.
            from ai_extract.services import bulk_service
            from ai_extract.repositories import layout_repository
            if layout_repository.latest_run(contract_obj.latest_version, completed=True) is None:
                return ServiceResult({'error': 'Hợp đồng chưa trích xuất xong; hãy chờ trích xuất hoàn tất rồi phân tích rủi ro.'}, status=409)
            job = bulk_service.start(user, [int(contract_id)], 'risk')
            return ServiceResult({'success': True, 'contract_id': contract_obj.id, 'job_id': job['id'], 'job_status': job['status']}, status=202)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=400)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

def submit_review(analysis_id, method, data, user=None):
    """
    POST: Submit legal expert review.
    """
    if method == 'POST':
        try:
            body = data
            comment = body.get('comment', '')
            final_risk_level = body.get('final_risk_level', 'MEDIUM')
        except (ValueError, KeyError):
            return ServiceResult({'error': 'Invalid request body.'}, status=400)
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
            user = user
            company = None if user.is_superuser else user.company
            data = analysis_history_service.list_all_analyses(company=company)
            return ServiceResult(data)
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=500)
    return ServiceResult({'error': 'Method not allowed.'}, status=405)

