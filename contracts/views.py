import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from .services import ContractService, RiskService, AnalysisHistoryService

contract_service = ContractService()
risk_service = RiskService()
analysis_history_service = AnalysisHistoryService()

def manager_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        user = request.user
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        if not user.role or user.role.role_name.upper() not in ['MANAGER', 'ADMIN']:
            return render(request, 'contracts/access_denied.html')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def api_manager_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Unauthorized. Please log in.'}, status=401)
        user = request.user
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        if not user.role or user.role.role_name.upper() not in ['MANAGER', 'ADMIN']:
            return JsonResponse({'error': 'Permission Denied: Only Managers can access this resource.'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@manager_required
def dashboard(request):
    """Render the dashboard SPA template."""
    return render(request, 'contracts/dashboard.html')


@manager_required
def workflow_board(request):
    """Render the workflow management board page."""
    return render(request, 'contracts/workflow_board.html')


@csrf_exempt
def api_workflow_all(request):
    """GET: Proxy — lấy tất cả workflows từ workflow-service."""
    import requests as req
    from django.conf import settings
    workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')
    try:
        resp = req.get(f"{workflow_url}/workflows/all/", timeout=10)
        resp.raise_for_status()
        return JsonResponse(resp.json())
    except Exception as e:
        return JsonResponse({'error': str(e), 'workflows': []}, status=200)


@csrf_exempt
def api_approve_workflow_step(request, step_id):
    """POST: Proxy — duyệt / từ chối 1 step trong workflow-service."""
    import requests as req
    from django.conf import settings
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')
    try:
        body = json.loads(request.body)
    except Exception:
        body = {}
    try:
        resp = req.post(
            f"{workflow_url}/workflows/steps/{step_id}/approve/",
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        return JsonResponse(resp.json())
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@manager_required
def contract_detail(request, contract_id):
    """Render the dedicated contract detail page."""
    from .models import Contract
    try:
        contract_obj = Contract.objects.get(id=contract_id)
        if not request.user.is_superuser and contract_obj.company != request.user.company:
            return render(request, 'contracts/access_denied.html')
    except Contract.DoesNotExist:
        from django.http import Http404
        raise Http404("Contract not found")
        
    version_id = request.GET.get('version_id')
    details = contract_service.get_contract_details(contract_id, version_id=version_id)
    if not details:
        from django.http import Http404
        raise Http404("Contract not found")
    return render(request, 'contracts/contract_detail.html', {'contract': details})


@csrf_exempt
@api_manager_required
def api_contracts_list(request):
    """
    GET: Get list of all contracts.
    """
    if request.method == 'GET':
        try:
            user = request.user
            company = None if user.is_superuser else user.company
            contracts = contract_service.list_all_contracts(company=company)
            return JsonResponse(contracts, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    elif request.method == 'POST':
        return api_create_contract(request)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
@api_manager_required
def api_create_contract(request):
    """
    POST: Create a contract, upload file/text, and trigger mock AI Analysis.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
        
    code = request.POST.get('contract_code')
    title = request.POST.get('title')
    contract_type = request.POST.get('contract_type', '')
    start_date = request.POST.get('start_date') or None
    end_date = request.POST.get('end_date') or None
    contract_value = request.POST.get('contract_value') or '0.00'
    raw_content = request.POST.get('raw_content')
    file_obj = request.FILES.get('file')

    if not code or not title:
        return JsonResponse({'error': 'Contract code and title are required.'}, status=400)

    try:
        company = None
        if request.user.is_authenticated:
            company = getattr(request.user, 'company', None)

        contract = contract_service.create_and_analyze_contract(
            code=code,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            contract_value=contract_value,
            file_obj=file_obj,
            raw_content=raw_content,
            company=company
        )
        return JsonResponse({
            'success': True,
            'contract_id': contract.id,
            'contract_code': contract.contract_code,
            'status': contract.status
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@api_manager_required
def api_contract_detail(request, contract_id):
    """
    GET: Get full detail of a contract.
    """
    if request.method == 'GET':
        from .models import Contract
        try:
            contract_obj = Contract.objects.get(id=contract_id)
            if not request.user.is_superuser and contract_obj.company != request.user.company:
                return JsonResponse({'error': 'Permission Denied: You do not have access to this contract.'}, status=403)
        except Contract.DoesNotExist:
            return JsonResponse({'error': 'Contract not found.'}, status=404)

        version_id = request.GET.get('version_id')
        details = contract_service.get_contract_details(contract_id, version_id=version_id)
        if not details:
            return JsonResponse({'error': 'Contract not found.'}, status=404)
        return JsonResponse(details)
        
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
@api_manager_required
def api_analyze_contract(request, contract_id):
    """
    POST: Run the AI analysis simulator for the given contract.
    """
    if request.method == 'POST':
        version_id = request.GET.get('version_id') or request.POST.get('version_id')
        if not version_id and request.body:
            try:
                body = json.loads(request.body)
                version_id = body.get('version_id')
            except Exception:
                pass
        try:
            from .models import Contract
            contract_obj = Contract.objects.get(id=contract_id)
            if not request.user.is_superuser and contract_obj.company != request.user.company:
                return JsonResponse({'error': 'Permission Denied.'}, status=403)
            contract = contract_service.analyze_contract(contract_id, version_id=version_id)
            return JsonResponse({
                'success': True,
                'contract_id': contract.id,
                'status': contract.status
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
@api_manager_required
def api_manual_extract_contract(request, contract_id):
    """
    POST: Run manual/local heuristic contract clause and entity extraction.
    """
    if request.method == 'POST':
        version_id = request.GET.get('version_id') or request.POST.get('version_id')
        if not version_id and request.body:
            try:
                body = json.loads(request.body)
                version_id = body.get('version_id')
            except Exception:
                pass
        try:
            from .models import Contract
            contract_obj = Contract.objects.get(id=contract_id)
            if not request.user.is_superuser and contract_obj.company != request.user.company:
                return JsonResponse({'error': 'Permission Denied.'}, status=403)
            contract = contract_service.manual_extract_contract(contract_id, version_id=version_id)
            return JsonResponse({
                'success': True,
                'contract_id': contract.id,
                'status': contract.status
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
@api_manager_required
def api_push_to_workflow(request, contract_id):
    """
    POST: Đẩy contract lên workflow-service để khởi tạo quy trình phê duyệt.
    """
    if request.method == 'POST':
        version_id = request.GET.get('version_id')
        if not version_id and request.body:
            try:
                body = json.loads(request.body)
                version_id = body.get('version_id')
            except Exception:
                pass
        try:
            result = contract_service.push_to_workflow(contract_id, version_id=version_id)
            return JsonResponse({'success': True, **result})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
def api_workflow_status(request, contract_id):
    """
    GET: Lấy trạng thái workflow hiện tại của contract từ workflow-service.
    """
    if request.method == 'GET':
        version_id = request.GET.get('version_id')
        try:
            result = contract_service.get_workflow_status(contract_id, version_id=version_id)
            if result is None:
                return JsonResponse({'workflow': None})
            return JsonResponse({'workflow': result})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
def api_contract_versions(request, contract_id):
    """
    GET: Get all versions of a contract.
    POST: Create a new version of the contract, parse clauses, and auto-run AI analysis.
    """
    if request.method == 'GET':
        details = contract_service.get_contract_details(contract_id)
        if not details:
            return JsonResponse({'error': 'Contract not found.'}, status=404)
        return JsonResponse({'versions': details.get('versions', [])})
        
    elif request.method == 'POST':
        change_summary = request.POST.get('change_summary', '')
        raw_content = request.POST.get('raw_content')
        file_obj = request.FILES.get('file')
        
        if not file_obj and not raw_content:
            return JsonResponse({'error': 'Either a file or text content is required for the new version.'}, status=400)
            
        try:
            # 1. Create the new version
            version = contract_service.create_new_version(
                contract_id=contract_id,
                file_obj=file_obj,
                raw_content=raw_content,
                change_summary=change_summary
            )
            
            # 2. Trigger AI analysis for the new version automatically
            scan_error = None
            try:
                contract_service.analyze_contract(contract_id, version_id=version.id)
            except Exception as se:
                scan_error = str(se)
                
            if scan_error:
                return JsonResponse({
                    'success': True,
                    'version_id': version.id,
                    'version_number': version.version_number,
                    'change_summary': version.change_summary,
                    'scan_error': scan_error
                })
            
            return JsonResponse({
                'success': True,
                'version_id': version.id,
                'version_number': version.version_number,
                'change_summary': version.change_summary
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)



@csrf_exempt
def api_submit_review(request, analysis_id):
    """
    POST: Submit legal expert review.
    """
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            comment = body.get('comment', '')
            final_risk_level = body.get('final_risk_level', 'MEDIUM')
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid request body.'}, status=400)

        if not comment:
            return JsonResponse({'error': 'Comment is required.'}, status=400)

        try:
            review = contract_service.submit_expert_review(
                analysis_id=analysis_id,
                comment=comment,
                final_risk_level=final_risk_level
            )
            return JsonResponse({
                'success': True,
                'review_id': review.id,
                'status': 'APPROVED'
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
def api_risks_list(request):
    """
    GET: Get list of all master risks.
    POST: Create a new master risk.
    """
    if request.method == 'GET':
        try:
            risks = risk_service.list_all_risks()
            return JsonResponse(risks, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    elif request.method == 'POST':
        try:
            body = json.loads(request.body) if request.body else {}
            name = body.get('risk_name')
            description = body.get('description', '')
            severity_level = body.get('severity_level', 'MEDIUM')
        except (ValueError, KeyError, TypeError):
            name = request.POST.get('risk_name')
            description = request.POST.get('description', '')
            severity_level = request.POST.get('severity_level', 'MEDIUM')

        if not name:
            name = request.POST.get('risk_name')
            description = request.POST.get('description', '') or description
            severity_level = request.POST.get('severity_level', 'MEDIUM') or severity_level

        try:
            risk = risk_service.create_new_risk(
                name=name,
                description=description,
                severity_level=severity_level
            )
            return JsonResponse({
                'success': True,
                'risk_id': risk.id,
                'risk_name': risk.rule_name,
                'severity_level': risk.severity
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@manager_required
def analysis_history(request):
    """Render the AI analysis history page."""
    return render(request, 'contracts/analysis_history.html')


@csrf_exempt
@api_manager_required
def api_analyses_list(request):
    """
    GET: Return full list of all AI analyses ordered by most recent.
    """
    if request.method == 'GET':
        try:
            user = request.user
            company = None if user.is_superuser else user.company
            data = analysis_history_service.list_all_analyses(company=company)
            return JsonResponse(data, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


def developer_test(request):
    """Render the developer test interface."""
    return render(request, 'contracts/developer_test.html')


@csrf_exempt
def api_run_developer_test(request):
    """
    POST: Run end-to-end test analysis on selected contract and return full payload & logs.
    """
    if request.method == 'POST':
        try:
            body = json.loads(request.body) if request.body else {}
            contract_id = body.get('contract_id')
        except Exception:
            contract_id = request.POST.get('contract_id')
            
        if not contract_id:
            return JsonResponse({'error': 'Contract ID is required.'}, status=400)
            
        try:
            from .models import Contract, RiskRule
            from django.conf import settings
            import requests
            from decimal import Decimal
            from django.db import connection
            
            contract = Contract.objects.get(id=contract_id)
            version = contract.latest_version
            if not version:
                from .models import ContractVersion
                version = ContractVersion.objects.create(contract=contract, version_number=1, change_summary="Initial version")
            
            raw_text = contract_service._get_raw_content(contract, version)
            parsed_clauses = contract_service._split_clauses(raw_text)
            
            existing_rules = RiskRule.objects.all().order_by('rule_name')
            
            # Format system prompt and rules instruction
            rules_instruction = ""
            if existing_rules:
                rules_instruction = "\n\nDanh sách các loại rủi ro hiện có trong hệ thống (hãy phân loại 'risk_category' trùng khớp với một trong số các tên này nếu điều khoản vi phạm, KHÔNG tự tạo thêm tên rủi ro mới nếu đã có sẵn tương đương):\n"
                for r in existing_rules:
                    rules_instruction += f"- '{r.rule_name}': {r.description or ''}\n"
                    
            system_prompt = (
                "Bạn là chuyên gia phân tích rủi ro hợp đồng pháp lý tại Việt Nam. "
                "Hãy đóng vai trò là một Luật sư cực kỳ nghiêm khắc, kỹ tính và luôn bảo vệ quyền lợi của Bên thuê/Bên mua. "
                "Nhiệm vụ của bạn là đọc kỹ điều khoản hợp đồng và phát hiện tất cả các lỗi, điểm bất lợi, rủi ro tiềm ẩn hoặc sự bất đối xứng quyền lợi. "
                "Luôn trả về JSON thuần túy với các trường sau: "
                "\"risk_category\" (str: Ví dụ 'Limitation of Liability Risk', 'Payment Risk', 'Unbalanced Termination Clause', hoặc tên rủi ro phù hợp), "
                "\"severity\" (str: 'NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'), "
                "\"risk_score\" (int 0-100), "
                "\"explanation\" (str: Giải thích chi tiết bằng tiếng Việt lý do điều khoản này có rủi ro hoặc bất lợi), "
                "\"recommendation\" (str: Đề xuất sửa đổi cụ thể bằng tiếng Việt để giảm thiểu rủi ro), "
                "\"disadvantaged_party\" (str: Bên gặp bất lợi, ví dụ 'Bên B', hoặc null). "
                f"Hãy suy luận cực kỳ chặt chẽ để tìm ra rủi ro. Nếu điều khoản thực sự hoàn toàn an toàn và không có bất kỳ rủi ro nào, hãy đặt \"severity\": \"NONE\", \"risk_score\": 0, \"risk_category\": \"Safe\" và \"disadvantaged_party\": null.{rules_instruction}"
            )
            
            payload = {
                "clauses": [
                    {"title": cl["title"], "content": cl["content"]}
                    for cl in parsed_clauses
                ],
                "extracted_entities": [],
                "risk_rules": [
                    {"name": r.rule_name, "description": r.description}
                    for r in existing_rules
                ]
            }
            
            # Call AI Service
            response = requests.post(
                f"{settings.AI_SERVICE_URL}/api/v1/analyze",
                json=payload,
                timeout=600
            )
            connection.close() # prevent postgres connection timeout
            response.raise_for_status()
            result = response.json()
            
            # Map findings and log status
            findings_log = []
            for f in result.get("findings", []):
                risk_name = f.get("risk_category", "Rủi ro chung").strip()
                # Check case-insensitively
                match = RiskRule.objects.filter(rule_name__iexact=risk_name).first()
                if match:
                    findings_log.append({
                        "clause_title": f.get("clause_title"),
                        "risk_category": match.rule_name,
                        "risk_code": match.rule_code,
                        "action": "REUSED_CASE_INSENSITIVE",
                        "severity": f.get("risk_level", "MEDIUM"),
                        "explanation": f.get("explanation"),
                        "recommendation": f.get("recommendation")
                    })
                else:
                    findings_log.append({
                        "clause_title": f.get("clause_title"),
                        "risk_category": risk_name,
                        "risk_code": risk_name.upper().replace(" ", "_").replace("-", "_"),
                        "action": "AUTO_CREATED_NEW",
                        "severity": f.get("risk_level", "MEDIUM"),
                        "explanation": f.get("explanation"),
                        "recommendation": f.get("recommendation")
                    })
            
            return JsonResponse({
                "success": True,
                "overall_score": result.get("overall_score"),
                "summary": result.get("summary"),
                "system_prompt": system_prompt,
                "payload_sent": payload,
                "raw_response": result,
                "mapped_findings": findings_log
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


# ─────────────────────────────────────────────
# BLOCKCHAIN API ENDPOINTS
# Gọi thẳng HTTP sang blockchain-service container.
# Chỉ giữ lại _bc_version_payload vì web container là nơi
# duy nhất có quyền truy cập file media (MEDIA_ROOT).
# ─────────────────────────────────────────────

import os as _os
import requests as _req
from django.conf import settings as _settings

_BC_URL = _os.environ.get("BLOCKCHAIN_SERVICE_URL", "http://blockchain-service:8000")


def _bc_version_payload(version):
    """Đọc nội dung file hợp đồng để tạo payload gửi sang blockchain-service."""
    content = None
    file_obj = version.files.first()
    if file_obj and file_obj.file_path:
        rel = file_obj.file_path.lstrip(_settings.MEDIA_URL)
        full = _os.path.join(str(_settings.MEDIA_ROOT), rel.replace('/', _os.sep))
        if _os.path.exists(full):
            try:
                from .crypto_utils import decrypt_pdf
                with open(full, 'rb') as f:
                    encrypted_data = f.read()
                decrypted_data = decrypt_pdf(encrypted_data)
                content = decrypted_data.decode('utf-8', errors='ignore')
            except Exception:
                pass

    # Find previous version of the same contract
    prev_version = version.contract.versions.filter(version_number=version.version_number - 1).first()
    prev_version_id = prev_version.id if prev_version else None

    return {
        "version_id": version.id,
        "content": content,
        "change_summary": version.change_summary or "",
        "contract_code": version.contract.contract_code,
        "version_number": version.version_number,
        "previous_version_id": prev_version_id
    }


def _get_version_or_latest(contract_id, version_id=None):
    from .models import Contract, ContractVersion
    try:
        contract = Contract.objects.get(id=contract_id)
    except Contract.DoesNotExist:
        return None, None, JsonResponse({'error': 'Contract not found.'}, status=404)
    if version_id:
        try:
            return contract, contract.versions.get(id=version_id), None
        except ContractVersion.DoesNotExist:
            return None, None, JsonResponse({'error': 'Version not found.'}, status=404)
    version = contract.latest_version
    if not version:
        return None, None, JsonResponse({'error': 'No version found.'}, status=404)
    return contract, version, None


@csrf_exempt
def api_blockchain_generate_proof(request, contract_id):
    """POST { version_id? } → /proofs/generate/ trên blockchain-service."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body) if request.body else {}
        contract, version, err = _get_version_or_latest(contract_id, body.get('version_id'))
        if err:
            return err
        resp = _req.post(f"{_BC_URL}/proofs/generate/", json=_bc_version_payload(version), timeout=15)
        result = resp.json()
        return JsonResponse({'success': resp.ok, 'contract_code': contract.contract_code,
                             'version_id': version.id, 'version_number': version.version_number, **result},
                            status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_blockchain_anchor_proof(request, contract_id):
    """POST { proof_id, network_id, smart_contract_id? } → /proofs/anchor/ trên blockchain-service."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body)
        if not body.get('proof_id') or not body.get('network_id'):
            return JsonResponse({'error': 'proof_id and network_id are required.'}, status=400)
        resp = _req.post(f"{_BC_URL}/proofs/anchor/", json={
            "proof_id": body['proof_id'],
            "network_id": body['network_id'],
            "smart_contract_id": body.get('smart_contract_id'),
        }, timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_blockchain_verify_proof(request, contract_id):
    """POST { version_id? } → /proofs/verify/ trên blockchain-service."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body) if request.body else {}
        contract, version, err = _get_version_or_latest(contract_id, body.get('version_id'))
        if err:
            return err
        resp = _req.post(f"{_BC_URL}/proofs/verify/", json=_bc_version_payload(version), timeout=15)
        result = resp.json()
        return JsonResponse({'contract_code': contract.contract_code,
                             'version_id': version.id, 'version_number': version.version_number, **result},
                            status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_blockchain_status(request, contract_id):
    """GET → trạng thái blockchain cho tất cả versions của hợp đồng."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        from .models import Contract
        contract = Contract.objects.get(id=contract_id)
        versions = []
        for v in contract.versions.order_by('version_number'):
            try:
                r = _req.post(f"{_BC_URL}/proofs/verify/", json=_bc_version_payload(v), timeout=15)
                bc_data = r.json()
            except Exception as ex:
                bc_data = {'verified': False, 'error': str(ex)}
            versions.append({'version_id': v.id, 'version_number': v.version_number,
                             'change_summary': v.change_summary or 'Initial version',
                             'blockchain': bc_data})
        return JsonResponse({'contract_id': contract.id, 'contract_code': contract.contract_code,
                             'versions': versions})
    except Contract.DoesNotExist:
        return JsonResponse({'error': 'Contract not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_blockchain_create_certificate(request):
    """POST { user_id, serial_number, issuer, valid_days? } → /certificates/create/ trên blockchain-service."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body)
        if not body.get('user_id') or not body.get('serial_number') or not body.get('issuer'):
            return JsonResponse({'error': 'user_id, serial_number và issuer là bắt buộc.'}, status=400)
        resp = _req.post(f"{_BC_URL}/certificates/create/", json={
            'user_id': body['user_id'],
            'serial_number': body['serial_number'],
            'issuer': body['issuer'],
            'valid_days': body.get('valid_days', 365),
        }, timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_blockchain_sign_step(request):
    """POST { step_id, user_id, certificate_id, signature_hash } → /signatures/create/ trên blockchain-service."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body)
        required = ['step_id', 'user_id', 'certificate_id', 'signature_hash']
        missing = [k for k in required if not body.get(k)]
        if missing:
            return JsonResponse({'error': f'Thiếu các trường: {", ".join(missing)}'}, status=400)
        resp = _req.post(f"{_BC_URL}/signatures/create/", json={
            'step_id': body['step_id'],
            'user_id': body['user_id'],
            'certificate_id': body['certificate_id'],
            'signature_hash': body['signature_hash'],
        }, timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_manager_required
def api_download_file(request, file_id):
    from django.conf import settings
    import os
    from django.http import HttpResponse, Http404
    from .models import ContractFile
    from .crypto_utils import decrypt_pdf
    
    try:
        cf = ContractFile.objects.get(id=file_id)
        if not request.user.is_superuser and cf.version.contract.company != request.user.company:
            return HttpResponse("Permission Denied: You do not have access to this file.", status=403)
    except ContractFile.DoesNotExist:
        raise Http404("File not found")
        
    rel_path = cf.file_path
    media_prefix = settings.MEDIA_URL
    if rel_path.startswith(media_prefix):
        rel_path = rel_path[len(media_prefix):]
        
    physical_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
    if not os.path.exists(physical_path):
        raise Http404("Physical file not found")
        
    try:
        with open(physical_path, 'rb') as f:
            encrypted_data = f.read()
        decrypted_data = decrypt_pdf(encrypted_data)
    except Exception as e:
        return HttpResponse(f"Error decrypting file: {str(e)}", status=500)
        
    response = HttpResponse(decrypted_data, content_type='application/octet-stream')
    if cf.file_name.lower().endswith('.pdf'):
        response['Content-Type'] = 'application/pdf'
    elif cf.file_name.lower().endswith('.txt'):
        response['Content-Type'] = 'text/plain'
        
    response['Content-Disposition'] = f'attachment; filename="{cf.file_name}"'
    return response


def api_blockchain_history(request, version_id):
    """GET → /history/<version_id>/ trên blockchain-service."""
    try:
        resp = _req.get(f"{_BC_URL}/history/{version_id}/", timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_blockchain_transaction(request, tx_hash):
    """GET → /transaction/<tx_hash>/ trên blockchain-service."""
    try:
        resp = _req.get(f"{_BC_URL}/transaction/{tx_hash}/", timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_blockchain_proof(request, version_id):
    """GET → /proof/<version_id>/ trên blockchain-service."""
    try:
        resp = _req.get(f"{_BC_URL}/proof/{version_id}/", timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_blockchain_certificate(request, user_id):
    """GET → /certificate/<user_id>/ trên blockchain-service."""
    try:
        resp = _req.get(f"{_BC_URL}/certificate/{user_id}/", timeout=15)
        return JsonResponse(resp.json(), status=resp.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def identity_registry(request):
    """Render the identity registry page."""
    return render(request, 'contracts/identity_registry.html')


@csrf_exempt
def api_register_company(request):
    """POST: Register a new Company in DB and anchor it to the blockchain."""
    import requests
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body)
        name = body.get('company_name')
        tax_code = body.get('tax_code')
        if not name or not tax_code:
            return JsonResponse({'error': 'Thiếu tên công ty hoặc mã số thuế'}, status=400)
            
        from .models import Company
        # Create in database
        company = Company.objects.create(
            company_name=name,
            tax_code=tax_code,
            status='ACTIVE'
        )
        
        # Anchor to blockchain via blockchain-service
        try:
            resp = requests.post(f"{_BC_URL}/company/register/", json={
                'company_id': company.id,
                'company_name': name,
                'tax_code': tax_code,
                'status': 'ACTIVE',
                'sender': 'System'
            }, timeout=20)
            
            if resp.status_code == 200:
                data = resp.json()
                company.tx_hash = data.get('tx_hash')
                company.block_number = data.get('block_number')
                company.block_hash = data.get('block_hash')
                company.save()
            else:
                error_msg = resp.json().get('error', 'Unknown blockchain error')
                company.status = 'ERROR'
                company.save()
                return JsonResponse({'error': f'Lỗi lưu blockchain: {error_msg}'}, status=400)
        except Exception as e:
            company.status = 'ERROR'
            company.save()
            return JsonResponse({'error': f'Không kết nối được dịch vụ blockchain: {str(e)}'}, status=500)
            
        return JsonResponse({
            'status': 'success',
            'company_id': company.id,
            'company_name': company.company_name,
            'tax_code': company.tax_code,
            'tx_hash': company.tx_hash,
            'block_number': company.block_number,
            'block_hash': company.block_hash
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_register_user(request):
    """POST: Register a new User in DB and anchor them to the blockchain."""
    import requests
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        body = json.loads(request.body)
        username = body.get('username')
        email = body.get('email')
        password = body.get('password')
        company_id = body.get('company_id')
        role_id = body.get('role_id')
        
        if not username or not email or not password or not company_id or not role_id:
            return JsonResponse({'error': 'Thiếu thông tin đăng ký nhân sự'}, status=400)
            
        from .models import Company, Role, User
        try:
            company = Company.objects.get(id=company_id)
            role = Role.objects.get(id=role_id)
        except (Company.DoesNotExist, Role.DoesNotExist) as e:
            return JsonResponse({'error': 'Công ty hoặc Vai trò không tồn tại'}, status=404)
            
        # Create in database
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            company=company,
            role=role,
            status='ACTIVE'
        )
        
        # Anchor to blockchain via blockchain-service
        try:
            resp = requests.post(f"{_BC_URL}/user/register/", json={
                'user_id': user.id,
                'username': username,
                'company_id': company.id,
                'role': role.role_name,
                'status': 'ACTIVE',
                'sender': 'System'
            }, timeout=20)
            
            if resp.status_code == 200:
                data = resp.json()
                user.tx_hash = data.get('tx_hash')
                user.block_number = data.get('block_number')
                user.block_hash = data.get('block_hash')
                user.save()
                
                # Automatically issue a digital certificate for the new user
                try:
                    import random
                    clean_company_name = "".join(x for x in company.company_name.upper() if x.isalnum() or x == ' ')
                    serial_number = f"CERT-{clean_company_name.replace(' ', '-')[:8]}-{user.id:04d}-{random.randint(1000, 9999)}"
                    requests.post(f"{_BC_URL}/certificates/create/", json={
                        'user_id': user.id,
                        'serial_number': serial_number,
                        'issuer': 'ContractGuard CA',
                        'valid_days': 365
                    }, timeout=10)
                except Exception as cert_err:
                    print(f"Warning: Failed to automatically issue certificate: {str(cert_err)}")
            else:
                error_msg = resp.json().get('error', 'Unknown blockchain error')
                user.status = 'ERROR'
                user.save()
                return JsonResponse({'error': f'Lỗi lưu blockchain: {error_msg}'}, status=400)
        except Exception as e:
            user.status = 'ERROR'
            user.save()
            return JsonResponse({'error': f'Không kết nối được dịch vụ blockchain: {str(e)}'}, status=500)
            
        return JsonResponse({
            'status': 'success',
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'company_name': company.company_name,
            'role_name': role.role_name,
            'tx_hash': user.tx_hash,
            'block_number': user.block_number,
            'block_hash': user.block_hash
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_companies_list(request):
    """GET: Get list of all companies."""
    from .models import Company
    companies = Company.objects.all().order_by('-id')
    data = []
    for c in companies:
        data.append({
            'id': c.id,
            'company_name': c.company_name,
            'tax_code': c.tax_code,
            'status': c.status,
            'tx_hash': c.tx_hash,
            'block_number': c.block_number,
            'block_hash': c.block_hash
        })
    return JsonResponse(data, safe=False)


def api_users_list(request):
    """GET: Get list of all users."""
    from .models import User
    users = User.objects.all().select_related('company', 'role').order_by('-id')
    data = []
    for u in users:
        data.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'company_name': u.company.company_name if u.company else 'N/A',
            'role_name': u.role.role_name if u.role else 'N/A',
            'status': u.status,
            'tx_hash': u.tx_hash,
            'block_number': u.block_number,
            'block_hash': u.block_hash
        })
    return JsonResponse(data, safe=False)


def api_roles_list(request):
    """GET: Get list of all roles."""
    from .models import Role
    # Ensure role MANAGER exists
    Role.objects.get_or_create(role_name='MANAGER')
    roles = Role.objects.all().order_by('role_name')
    data = [{'id': r.id, 'role_name': r.role_name} for r in roles]
    return JsonResponse(data, safe=False)


def login_user(request):
    """Render and handle the login page."""
    from .models import Role
    Role.objects.get_or_create(role_name='MANAGER')
    
    if request.user.is_authenticated:
        return redirect('/')
        
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        next_url = request.POST.get('next', '/') or '/'
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url)
        else:
            error = "Tài khoản hoặc mật khẩu không chính xác."
            
    next_url = request.GET.get('next', '/')
    return render(request, 'contracts/login.html', {
        'error': error,
        'next': next_url
    })


def signup_user(request):
    """Render and handle the signup page."""
    from .models import Company, Role, User
    Role.objects.get_or_create(role_name='MANAGER')
    
    if request.user.is_authenticated:
        return redirect('/')
        
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        company_id = request.POST.get('company_id')
        role_id = request.POST.get('role_id')
        
        if not username or not email or not password or not company_id or not role_id:
            error = "Vui lòng điền đầy đủ các trường thông tin."
        elif User.objects.filter(username=username).exists():
            error = "Tên đăng nhập đã tồn tại."
        elif User.objects.filter(email=email).exists():
            error = "Email đã được sử dụng."
        else:
            try:
                company = Company.objects.get(id=company_id)
                role = Role.objects.get(id=role_id)
                
                # Create the user in database
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    company=company,
                    role=role,
                    status='ACTIVE'
                )
                
                # Register on the blockchain-service
                try:
                    import requests
                    resp = requests.post(f"{_BC_URL}/user/register/", json={
                        'user_id': user.id,
                        'username': username,
                        'company_id': company.id,
                        'role': role.role_name,
                        'status': 'ACTIVE',
                        'sender': 'System'
                    }, timeout=15)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        user.tx_hash = data.get('tx_hash')
                        user.block_number = data.get('block_number')
                        user.block_hash = data.get('block_hash')
                        user.save()
                        
                        # Automatically issue a digital certificate for the new user
                        try:
                            import random
                            clean_company_name = "".join(x for x in company.company_name.upper() if x.isalnum() or x == ' ')
                            serial_number = f"CERT-{clean_company_name.replace(' ', '-')[:8]}-{user.id:04d}-{random.randint(1000, 9999)}"
                            requests.post(f"{_BC_URL}/certificates/create/", json={
                                'user_id': user.id,
                                'serial_number': serial_number,
                                'issuer': 'ContractGuard CA',
                                'valid_days': 365
                            }, timeout=10)
                        except Exception as cert_err:
                            print(f"Warning: Failed to automatically issue certificate: {str(cert_err)}")
                    else:
                        user.status = 'ERROR'
                        user.save()
                except Exception as e:
                    print(f"Warning: Failed to register user on blockchain: {str(e)}")
                    user.status = 'ERROR'
                    user.save()
                
                # Automatically log the user in after signing up
                login(request, user)
                return redirect('/')
            except Exception as e:
                error = f"Lỗi đăng ký: {str(e)}"
                
    companies = Company.objects.all().order_by('company_name')
    roles = Role.objects.all().order_by('role_name')
    return render(request, 'contracts/signup.html', {
        'companies': companies,
        'roles': roles,
        'error': error
    })


def logout_user(request):
    """Log the user out and redirect to the login page."""
    logout(request)
    return redirect('/login/')


