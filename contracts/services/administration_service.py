from contracts.repositories import administration_data_repository as data_repository
import os as _os
import requests as _req
from contracts.services.results import ServiceResult

def admin_stats(query):
    """GET → stats, service health checks, and recent audit logs."""
    import time
    total_users = data_repository.count_user_for_admin_stats()
    total_companies = data_repository.count_company_for_admin_stats()
    total_contracts = data_repository.count_contract_for_admin_stats()
    from django.conf import settings as _settings
    # The ledger is Fabric, reached through its gateway; the blockchain service keeps the ledger book.
    health_services = {'Fabric Gateway': getattr(_settings, 'FABRIC_GATEWAY_URL', 'http://fabric-gateway:5000').rstrip('/') + '/health',
                       'Blockchain Service (ledger book)': getattr(_settings, 'BLOCKCHAIN_SERVICE_URL', 'http://blockchain-service:8000').rstrip('/') + '/health/',
                       'Workflow Service': _os.environ.get('WORKFLOW_SERVICE_URL', 'http://localhost:8003'),
                       'AI Service': (getattr(_settings, 'AI_SERVICE_URL', '') or 'http://ai:8000') + '/internal/ai/qwen/'}
    health_results = {}
    for name, url in health_services.items():
        status = 'OFFLINE'
        latency = 0.0
        try:
            start_time = time.time()
            if name == 'MCP Server':
                r = _req.post(url, json={'jsonrpc': '2.0', 'method': 'ping', 'id': 1}, timeout=2)
            else:
                r = _req.get(url, timeout=2)
            latency = round((time.time() - start_time) * 1000, 1)
            if r.status_code < 500:
                status = 'ONLINE'
        except Exception:
            status = 'OFFLINE'
        health_results[name] = {'status': status, 'latency': latency, 'url': url}
    try:
        page = int(query.get('page', 1))
    except ValueError:
        page = 1
    limit = 10
    offset = (page - 1) * limit
    total_logs = data_repository.count_audit_log_for_admin_stats()
    logs = data_repository.order_by_audit_log_for_admin_stats()[offset:offset + limit]
    logs_data = []
    for l in logs:
        logs_data.append({'id': l.id, 'user': l.user.username if l.user else 'System', 'action': l.action, 'contract_code': l.contract.contract_code if l.contract else None, 'ip_address': l.ip_address or 'N/A', 'payload': l.payload, 'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S')})
    users = data_repository.order_by_user_for_admin_stats()
    users_data = []
    for u in users:
        users_data.append({'id': u.id, 'username': u.username, 'email': u.email, 'company_name': u.company.company_name if u.company else 'N/A', 'role_name': u.role.role_name if u.role else 'Staff', 'status': u.status, 'block_number': u.block_number, 'tx_hash': u.tx_hash})
    return ServiceResult({'stats': {'total_users': total_users, 'total_companies': total_companies, 'total_contracts': total_contracts}, 'health': health_results, 'logs': logs_data, 'logs_pagination': {'page': page, 'total_logs': total_logs, 'limit': limit, 'total_pages': (total_logs + limit - 1) // limit if total_logs > 0 else 1}, 'users': users_data, 'skip_ocr': _os.environ.get('SKIP_OCR', 'False').lower() in ('true', '1', 'yes')})

def admin_delete_user(user_id, user):
    if user.pk == user_id:
        return ServiceResult({'error': 'Cannot delete your own account'}, status=400)
    'POST -> Delete a user from the local database.'
    from contracts.models import User
    try:
        user = data_repository.get_user_for_admin_delete_user(user_id)
        data_repository.delete_user_for_admin_delete_user(user)
        return ServiceResult({'status': 'success', 'deleted_id': user_id})
    except User.DoesNotExist:
        return ServiceResult({'error': 'User not found'}, status=404)
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=500)

def admin_retry_user(user_id, user, data, authorization_headers):
    """POST -> Issue the blockchain certificate of a user left in ERROR, then activate the user."""
    import requests
    from contracts.models import User
    try:
        user = data_repository.get_user_for_admin_delete_user(user_id)
        if not user.company or not user.role:
            return ServiceResult({'error': 'User missing company or role'}, status=400)
        # Issue the certificate the registration could not get from the blockchain service.
        from contracts.services.ledger_book_service import register_user as issue_certificate, LedgerBookError
        try:
            certificate = issue_certificate(user, user.company, user.role)
        except LedgerBookError as e:
            return ServiceResult({'error': f'Blockchain service: {str(e)}'}, status=502)
        user.status = 'ACTIVE'
        data_repository.save_user_for_admin_retry_user(user)
        return ServiceResult({'status': 'success', 'user_id': user.id, 'certificate_serial': certificate.get('serial_number')})
    except User.DoesNotExist:
        return ServiceResult({'error': 'User not found'}, status=404)
    except Exception as e:
        return ServiceResult({'error': str(e)}, status=500)

def admin_toggle_ocr(user, method, data, metadata):
    """GET or POST → view or toggle dynamic OCR engine setting."""
    if method == 'GET':
        skip_ocr = _os.environ.get('SKIP_OCR', 'False').lower() in ('true', '1', 'yes')
        return ServiceResult({'skip_ocr': skip_ocr})
    elif method == 'POST':
        try:
            body = data
            skip_ocr = body.get('skip_ocr', True)
            _os.environ['SKIP_OCR'] = 'True' if skip_ocr else 'False'
            data_repository.create_audit_log_for_admin_toggle_ocr(metadata, skip_ocr, user)
            return ServiceResult({'status': 'success', 'skip_ocr': skip_ocr})
        except Exception as e:
            return ServiceResult({'error': str(e)}, status=500)
    return ServiceResult({'error': 'Method not allowed'}, status=405)
