import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import ContractService, RiskService, AnalysisHistoryService

contract_service = ContractService()
risk_service = RiskService()
analysis_history_service = AnalysisHistoryService()

def dashboard(request):
    """Render the dashboard SPA template."""
    return render(request, 'contracts/dashboard.html')


def contract_detail(request, contract_id):
    """Render the dedicated contract detail page."""
    version_id = request.GET.get('version_id')
    details = contract_service.get_contract_details(contract_id, version_id=version_id)
    if not details:
        from django.http import Http404
        raise Http404("Contract not found")
    return render(request, 'contracts/contract_detail.html', {'contract': details})



@csrf_exempt
def api_contracts_list(request):
    """
    GET: Get list of all contracts.
    POST: Create a contract, upload file/text, and trigger mock AI Analysis.
    """
    if request.method == 'GET':
        try:
            contracts = contract_service.list_all_contracts()
            return JsonResponse(contracts, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    elif request.method == 'POST':
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
            contract = contract_service.create_and_analyze_contract(
                code=code,
                title=title,
                contract_type=contract_type,
                start_date=start_date,
                end_date=end_date,
                contract_value=contract_value,
                file_obj=file_obj,
                raw_content=raw_content
            )
            return JsonResponse({
                'success': True,
                'contract_id': contract.id,
                'contract_code': contract.contract_code,
                'status': contract.status
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
def api_contract_detail(request, contract_id):
    """
    GET: Get full detail of a contract.
    """
    if request.method == 'GET':
        version_id = request.GET.get('version_id')
        details = contract_service.get_contract_details(contract_id, version_id=version_id)
        if not details:
            return JsonResponse({'error': 'Contract not found.'}, status=404)
        return JsonResponse(details)
        
    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
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


def analysis_history(request):
    """Render the AI analysis history page."""
    return render(request, 'contracts/analysis_history.html')


@csrf_exempt
def api_analyses_list(request):
    """
    GET: Return full list of all AI analyses ordered by most recent.
    """
    if request.method == 'GET':
        try:
            data = analysis_history_service.list_all_analyses()
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
