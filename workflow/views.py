import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import WorkflowRecommendationService, DynamicWorkflowBuilderService


# ─────────────────────────────────────────────
# PAGE VIEWS
# ─────────────────────────────────────────────

def workflow_dashboard(request):
    """Render the Workflow AI dashboard page."""
    return render(request, 'workflow/workflow_dashboard.html')


def workflow_recommendation(request):
    """Render the Workflow Recommendation page."""
    return render(request, 'workflow/workflow_recommendation.html')


def workflow_builder(request):
    """Render the Dynamic Workflow Builder page."""
    return render(request, 'workflow/workflow_builder.html')


# ─────────────────────────────────────────────
# API VIEWS
# ─────────────────────────────────────────────

@csrf_exempt
def api_workflow_recommend(request):
    """
    POST: Generate a workflow recommendation from contract data (mock).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    contract_data = {
        'title': body.get('title', ''),
        'contract_type': body.get('contract_type', ''),
        'department': body.get('department', ''),
        'contract_value': body.get('contract_value', 0),
        'risk_level': body.get('risk_level', 'MEDIUM'),
        'content': body.get('content', ''),
    }

    try:
        recommendation_service = WorkflowRecommendationService()
        result = recommendation_service.recommend(contract_data)
        return JsonResponse({'success': True, **result})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def api_workflow_build(request):
    """
    POST: Generate a dynamic workflow from contract data and business rules (mock).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    contract_data = {
        'title': body.get('title', ''),
        'contract_type': body.get('contract_type', ''),
        'department': body.get('department', ''),
        'contract_value': body.get('contract_value', 0),
        'risk_level': body.get('risk_level', 'MEDIUM'),
        'content': body.get('content', ''),
    }

    business_rules = body.get('business_rules', {})

    try:
        builder_service = DynamicWorkflowBuilderService()
        result = builder_service.build(contract_data, business_rules)
        return JsonResponse({'success': True, **result})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
