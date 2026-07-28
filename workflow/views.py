"""
workflow/views.py

Thin view layer for the Workflow AI module.
Each API view follows a strict four-step pipeline:
  1. Parse request body
  2. Validate (via WorkflowValidator)
  3. Map body to DTO (via RequestMapper)
  4. Call service and return JSON response

No business logic, no field defaults, no transformation lives here.
"""
import json

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .services import WorkflowRecommendationService, DynamicWorkflowBuilderService, WorkflowTemplateService
from .validators import RecommendationValidator, BuilderValidator, TemplateCreateValidator, TemplateImportValidator
from .mappers import RequestMapper
from .exceptions import WorkflowValidationException, WorkflowServiceException
from .dto import RecommendationResponse, BuilderResponse


_template_service = WorkflowTemplateService()


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
    POST /workflow/api/recommend/

    Generate a workflow recommendation from contract data.
    Returns the same JSON structure as before; only the internal
    pipeline has been reorganised.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    # 1. Parse
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    # 2. Validate
    try:
        RecommendationValidator.validate(body)
    except WorkflowValidationException as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    # 3. Map to DTO
    recommendation_request = RequestMapper.to_recommendation_request(body)

    # 4. Call service → wrap in output DTO → serialise
    try:
        service = WorkflowRecommendationService()
        result = service.recommend(recommendation_request.to_dict())
        response_dto = RecommendationResponse(
            workflow_name=result['workflow_name'],
            confidence=result['confidence'],
            reasoning=result.get('reasoning', []),
            steps=result.get('steps', []),
        )
        return JsonResponse({'success': True, **response_dto.to_api_dict()})
    except WorkflowServiceException as exc:
        return JsonResponse({'error': str(exc)}, status=500)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


@csrf_exempt
def api_workflow_build(request):
    """
    POST /workflow/api/build/

    Generate a dynamic workflow from contract data and business rules.
    Returns the same JSON structure as before; only the internal
    pipeline has been reorganised.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    # 1. Parse
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    # 2. Validate
    try:
        BuilderValidator.validate(body)
    except WorkflowValidationException as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    # 3. Map to DTO
    builder_request = RequestMapper.to_builder_request(body)

    # 4. Call service → wrap in output DTO → serialise
    try:
        service = DynamicWorkflowBuilderService()
        result = service.build(
            builder_request.to_contract_dict(),
            builder_request.business_rules.to_dict(),
        )
        response_dto = BuilderResponse(
            workflow=result['workflow'],
            total_estimated_days=result['total_estimated_days'],
            generated_from=result['generated_from'],
        )
        return JsonResponse({'success': True, **response_dto.to_api_dict()})
    except WorkflowServiceException as exc:
        return JsonResponse({'error': str(exc)}, status=500)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ─────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────

def _parse_body(request) -> dict | None:
    """
    Safely parse the request body as JSON.
    Returns a dict on success, None on failure.
    """
    try:
        return json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        return None


# ─────────────────────────────────────────────
# TEMPLATE PAGE VIEW
# ─────────────────────────────────────────────

def workflow_templates(request):
    """Render the Workflow Templates management page."""
    return render(request, 'workflow/workflow_templates.html')


# ─────────────────────────────────────────────
# TEMPLATE API VIEWS
# ─────────────────────────────────────────────

@csrf_exempt
def api_templates_list(request):
    """
    GET  /workflow/api/templates/      → list all templates
    POST /workflow/api/templates/      → create a new custom template
    """
    if request.method == 'GET':
        try:
            templates = _template_service.list_templates()
            return JsonResponse({'success': True, 'templates': templates})
        except WorkflowServiceException as exc:
            return JsonResponse({'error': str(exc)}, status=500)

    if request.method == 'POST':
        body = _parse_body(request)
        if body is None:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)
        try:
            TemplateCreateValidator.validate(body)
        except WorkflowValidationException as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        try:
            template = _template_service.create_template(body)
            return JsonResponse({'success': True, 'template': template}, status=201)
        except WorkflowServiceException as exc:
            return JsonResponse({'error': str(exc)}, status=500)

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@csrf_exempt
def api_template_detail(request, template_id):
    """
    GET /workflow/api/templates/<id>/  → retrieve a single template
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        template = _template_service.get_template(template_id)
        return JsonResponse({'success': True, 'template': template})
    except WorkflowServiceException as exc:
        status = 404 if exc.code == 'NOT_FOUND' else 500
        return JsonResponse({'error': str(exc)}, status=status)


@csrf_exempt
def api_template_duplicate(request, template_id):
    """
    POST /workflow/api/templates/<id>/duplicate/  → clone a template
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        clone = _template_service.duplicate_template(template_id)
        return JsonResponse({'success': True, 'template': clone}, status=201)
    except WorkflowServiceException as exc:
        status = 404 if exc.code == 'NOT_FOUND' else 500
        return JsonResponse({'error': str(exc)}, status=status)


@csrf_exempt
def api_template_delete(request, template_id):
    """
    DELETE /workflow/api/templates/<id>/delete/  → remove a custom template
    """
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        _template_service.delete_template(template_id)
        return JsonResponse({'success': True, 'deleted_id': template_id})
    except WorkflowValidationException as exc:
        return JsonResponse({'error': str(exc)}, status=403)
    except WorkflowServiceException as exc:
        status = 404 if exc.code == 'NOT_FOUND' else 500
        return JsonResponse({'error': str(exc)}, status=status)


@csrf_exempt
def api_template_import(request):
    """
    POST /workflow/api/templates/import/  → import a template from JSON
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)
    try:
        TemplateImportValidator.validate(body)
    except WorkflowValidationException as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    try:
        template = _template_service.import_template(body)
        return JsonResponse({'success': True, 'template': template}, status=201)
    except WorkflowServiceException as exc:
        return JsonResponse({'error': str(exc)}, status=500)

