import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import ContractService, RiskService

contract_service = ContractService()
risk_service = RiskService()

def dashboard(request):
    """Render the dashboard SPA template."""
    return render(request, 'contracts/dashboard.html')


def contract_detail(request, contract_id):
    """Render the dedicated contract detail page."""
    details = contract_service.get_contract_details(contract_id)
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
        details = contract_service.get_contract_details(contract_id)
        if not details:
            return JsonResponse({'error': 'Contract not found.'}, status=404)
        return JsonResponse(details)
        
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
                'risk_name': risk.risk_name,
                'severity_level': risk.severity_level
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Method not allowed.'}, status=405)
