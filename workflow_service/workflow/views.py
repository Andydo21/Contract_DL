import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import WorkflowService

workflow_service = WorkflowService()

def index(request):
    return JsonResponse({"status": "healthy", "service": "workflow_service"})


def list_all_workflows(request):
    """GET /workflows/all/ — Liệt kê tất cả workflows kèm steps."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    workflows = workflow_service.list_all_workflows()
    result = []
    for wf in workflows:
        result.append({
            "workflow_id":   wf.id,
            "version_id":    wf.version_id,
            "workflow_name": wf.workflow_name,
            "status":        wf.status,
            "workflow_type": wf.workflow_type,
            "reasons":       wf.reasons,
            "started_at":    wf.started_at.isoformat() if wf.started_at else None,
            "completed_at":  wf.completed_at.isoformat() if wf.completed_at else None,
            "steps": [
                {
                    "id":           st.id,
                    "step_order":   st.step_order,
                    "step_name":    st.step_name,
                    "role_id":      st.role_id,
                    "status":       st.status,
                    "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                    "comment":      st.approvals.order_by('-id').first().comment if st.approvals.exists() else None,
                }
                for st in wf.steps.order_by("step_order")
            ],
        })
    return JsonResponse({"workflows": result})


@csrf_exempt
def create_workflow(request):
    """POST /workflows/ — Tạo workflow + steps cho 1 contract version."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    version_id    = body.get("version_id")
    workflow_name = body.get("workflow_name", "Contract Approval Workflow")
    steps_data    = body.get("steps", [])

    contract_text = body.get("contract_text", "")
    clause_types  = body.get("clause_types", [])
    contract_type = body.get("contract_type", "")

    if not version_id:
        return JsonResponse({"error": "version_id is required"}, status=400)

    try:
        workflow = workflow_service.create_workflow(
            version_id=version_id,
            workflow_name=workflow_name,
            contract_text=contract_text,
            clause_types=clause_types,
            contract_type=contract_type,
            steps_data=steps_data
        )
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=409 if "active" in str(ve) else 400)

    return JsonResponse({
        "success":       True,
        "workflow_id":   workflow.id,
        "workflow_name": workflow.workflow_name,
        "status":        workflow.status,
        "workflow_type": workflow.workflow_type,
        "reasons":       workflow.reasons,
        "steps": [
            {"id": st.id, "step_order": st.step_order, "step_name": st.step_name, "role_id": st.role_id, "status": st.status}
            for st in workflow.steps.order_by("step_order")
        ],
    }, status=201)


def get_workflow(request, version_id):
    """GET /workflows/<version_id>/ — Lấy workflow mới nhất của 1 contract version."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    workflow = workflow_service.get_workflow(version_id)
    if not workflow:
        return JsonResponse({"error": "No workflow found for this version"}, status=404)

    return JsonResponse({
        "workflow_id":   workflow.id,
        "workflow_name": workflow.workflow_name,
        "status":        workflow.status,
        "workflow_type": workflow.workflow_type,
        "reasons":       workflow.reasons,
        "started_at":    workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at":  workflow.completed_at.isoformat() if workflow.completed_at else None,
        "steps": [
            {
                "id":           st.id,
                "step_order":   st.step_order,
                "step_name":    st.step_name,
                "role_id":      st.role_id,
                "status":       st.status,
                "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                "comment":      st.approvals.order_by('-id').first().comment if st.approvals.exists() else None,
            }
            for st in workflow.steps.order_by("step_order")
        ],
    })


def get_workflow_by_id_view(request, workflow_id):
    """GET /workflows/detail/<workflow_id>/ — Lấy chi tiết workflow theo workflow_id."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    workflow = workflow_service.get_workflow_by_id(workflow_id)
    if not workflow:
        return JsonResponse({"error": "Workflow not found"}, status=404)

    return JsonResponse({
        "workflow_id":   workflow.id,
        "workflow_name": workflow.workflow_name,
        "status":        workflow.status,
        "workflow_type": workflow.workflow_type,
        "reasons":       workflow.reasons,
        "version_id":    workflow.version_id,
        "started_at":    workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at":  workflow.completed_at.isoformat() if workflow.completed_at else None,
        "steps": [
            {
                "id":           st.id,
                "step_order":   st.step_order,
                "step_name":    st.step_name,
                "role_id":      st.role_id,
                "status":       st.status,
                "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                "comment":      st.approvals.order_by('-id').first().comment if st.approvals.exists() else None,
            }
            for st in workflow.steps.order_by("step_order")
        ],
    })


@csrf_exempt
def approve_step(request, step_id):
    """POST /workflows/steps/<step_id>/approve/ — Duyệt hoặc từ chối 1 step."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    user_id = body.get("user_id", 1)
    comment = body.get("comment", "")
    action  = body.get("action", "APPROVED")

    try:
        step = workflow_service.approve_step(
            step_id=step_id,
            user_id=user_id,
            action=action,
            comment=comment
        )
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400 if "action" in str(ve) else 404)

    return JsonResponse({
        "success":         True,
        "step_id":         step.id,
        "step_status":     step.status,
        "workflow_status": step.workflow.status,
        "version_id":      step.workflow.version_id,
    })
