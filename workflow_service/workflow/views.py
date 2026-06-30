import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Workflow, WorkflowStep, Approval


def index(request):
    return JsonResponse({"status": "healthy", "service": "workflow_service"})


def list_all_workflows(request):
    """GET /workflows/all/ — Liệt kê tất cả workflows kèm steps."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    workflows = Workflow.objects.all().order_by("-id")
    result = []
    for wf in workflows:
        result.append({
            "workflow_id":   wf.id,
            "version_id":    wf.version_id,
            "workflow_name": wf.workflow_name,
            "status":        wf.status,
            "started_at":    wf.started_at.isoformat() if wf.started_at else None,
            "completed_at":  wf.completed_at.isoformat() if wf.completed_at else None,
            "steps": [
                {
                    "id":           st.id,
                    "step_order":   st.step_order,
                    "step_name":    st.step_name,
                    "status":       st.status,
                    "completed_at": st.completed_at.isoformat() if st.completed_at else None,
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

    if not version_id:
        return JsonResponse({"error": "version_id is required"}, status=400)

    # Chỉ cho phép 1 workflow active per version
    if Workflow.objects.filter(version_id=version_id, status__in=["PENDING", "IN_PROGRESS"]).exists():
        return JsonResponse({"error": "A workflow is already active for this contract version"}, status=409)

    workflow = Workflow.objects.create(
        version_id=version_id,
        workflow_name=workflow_name,
        status="PENDING",
        started_at=timezone.now(),
    )

    if not steps_data:
        steps_data = [
            {"step_order": 1, "step_name": "Legal Review"},
            {"step_order": 2, "step_name": "Manager Approval"},
            {"step_order": 3, "step_name": "Sign & Archive"},
        ]

    for s in steps_data:
        WorkflowStep.objects.create(
            workflow=workflow,
            step_order=s.get("step_order", 1),
            step_name=s.get("step_name", "Review"),
            status="PENDING",
        )

    return JsonResponse({
        "success":       True,
        "workflow_id":   workflow.id,
        "workflow_name": workflow.workflow_name,
        "status":        workflow.status,
        "steps": [
            {"id": st.id, "step_order": st.step_order, "step_name": st.step_name, "status": st.status}
            for st in workflow.steps.order_by("step_order")
        ],
    }, status=201)


def get_workflow(request, version_id):
    """GET /workflows/<version_id>/ — Lấy workflow mới nhất của 1 contract version."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    workflow = Workflow.objects.filter(version_id=version_id).order_by("-id").first()
    if not workflow:
        return JsonResponse({"error": "No workflow found for this version"}, status=404)

    return JsonResponse({
        "workflow_id":   workflow.id,
        "workflow_name": workflow.workflow_name,
        "status":        workflow.status,
        "started_at":    workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at":  workflow.completed_at.isoformat() if workflow.completed_at else None,
        "steps": [
            {
                "id":           st.id,
                "step_order":   st.step_order,
                "step_name":    st.step_name,
                "status":       st.status,
                "completed_at": st.completed_at.isoformat() if st.completed_at else None,
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

    try:
        step = WorkflowStep.objects.get(id=step_id)
    except WorkflowStep.DoesNotExist:
        return JsonResponse({"error": "Step not found"}, status=404)

    user_id = body.get("user_id", 1)
    comment = body.get("comment", "")
    action  = body.get("action", "APPROVED")

    if action not in ("APPROVED", "REJECTED"):
        return JsonResponse({"error": "action must be APPROVED or REJECTED"}, status=400)

    Approval.objects.create(
        step=step,
        user_id=user_id,
        status=action,
        comment=comment,
        approved_at=timezone.now(),
    )

    step.status       = action
    step.completed_at = timezone.now()
    step.save()

    workflow = step.workflow

    if action == "REJECTED":
        workflow.status       = "REJECTED"
        workflow.completed_at = timezone.now()
        workflow.save()
    else:
        if all(s.status == "APPROVED" for s in workflow.steps.all()):
            workflow.status       = "COMPLETED"
            workflow.completed_at = timezone.now()
            workflow.save()
        else:
            workflow.status = "IN_PROGRESS"
            workflow.save()

    return JsonResponse({
        "success":         True,
        "step_id":         step.id,
        "step_status":     step.status,
        "workflow_status": workflow.status,
    })
