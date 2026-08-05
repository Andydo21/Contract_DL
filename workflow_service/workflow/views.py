import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services import WorkflowService, KeyManagementService

workflow_service = WorkflowService()


def index(request):
    return JsonResponse({"status": "healthy", "service": "workflow_service"})


def list_all_workflows(request):
    """GET /workflows/all/"""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    workflows = workflow_service.list_all_workflows()
    result = [{
        "workflow_id":   wf.id,
        "version_id":    wf.version_id,
        "workflow_name": wf.workflow_name,
        "status":        wf.status,
        "workflow_type": wf.workflow_type,
        "reasons":       wf.reasons,
        "started_at":    wf.started_at.isoformat() if wf.started_at else None,
        "completed_at":  wf.completed_at.isoformat() if wf.completed_at else None,
        "steps": [_step_to_dict(st) for st in wf.steps.order_by("step_order")],
    } for wf in workflows]
    return JsonResponse({"workflows": result})


@csrf_exempt
def create_workflow(request):
    """POST /workflows/"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    version_id = body.get("version_id")
    if not version_id:
        return JsonResponse({"error": "version_id is required"}, status=400)

    try:
        workflow = workflow_service.create_workflow(
            version_id=version_id,
            workflow_name=body.get("workflow_name", "Contract Approval Workflow"),
            contract_text=body.get("contract_text", ""),
            clause_types=body.get("clause_types", []),
            contract_type=body.get("contract_type", ""),
            steps_data=body.get("steps", [])
        )
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=409 if "active" in str(ve) else 400)

    return JsonResponse({
        "success": True,
        "workflow_id": workflow.id,
        "workflow_name": workflow.workflow_name,
        "status": workflow.status,
        "workflow_type": workflow.workflow_type,
        "reasons": workflow.reasons,
        "steps": [_step_to_dict(st) for st in workflow.steps.order_by("step_order")],
    }, status=201)


def get_workflow(request, version_id):
    """GET /workflows/<version_id>/"""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    workflow = workflow_service.get_workflow(version_id)
    if not workflow:
        return JsonResponse({"error": "No workflow found for this version"}, status=404)
    return JsonResponse({
        "workflow_id": workflow.id, "workflow_name": workflow.workflow_name,
        "status": workflow.status, "workflow_type": workflow.workflow_type,
        "reasons": workflow.reasons, "version_id": workflow.version_id,
        "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        "steps": [_step_to_dict(st) for st in workflow.steps.order_by("step_order")],
    })


def get_workflow_by_id_view(request, workflow_id):
    """GET /workflows/detail/<workflow_id>/"""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    workflow = workflow_service.get_workflow_by_id(workflow_id)
    if not workflow:
        return JsonResponse({"error": "Workflow not found"}, status=404)
    return JsonResponse({
        "workflow_id": workflow.id, "workflow_name": workflow.workflow_name,
        "status": workflow.status, "workflow_type": workflow.workflow_type,
        "reasons": workflow.reasons, "version_id": workflow.version_id,
        "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        "steps": [_step_to_dict(st) for st in workflow.steps.order_by("step_order")],
    })


@csrf_exempt
def approve_step(request, step_id):
    """POST /workflows/steps/<step_id>/approve/"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    try:
        step = workflow_service.approve_step(
            step_id=step_id,
            user_id=body.get("user_id", 1),
            action=body.get("action", "APPROVED"),
            comment=body.get("comment", ""),
            company_id=body.get("company_id"),
        )
    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400 if "action" in str(ve) else 404)

    return JsonResponse({
        "success": True,
        "step_id": step.id,
        "step_status": step.status,
        "workflow_status": step.workflow.status,
        "version_id": step.workflow.version_id,
    })


# ─────────────────────────────────────────────────────────────────
#  KEY MANAGEMENT VIEWS
# ─────────────────────────────────────────────────────────────────

@csrf_exempt
def key_list_create(request):
    """GET /keys/?company_id=X  |  POST /keys/"""
    if request.method == "GET":
        try:
            company_id = request.GET.get("company_id")
            keys = KeyManagementService.list_keys(company_id=int(company_id) if company_id else None)
            return JsonResponse({"keys": [_key_to_dict(k) for k in keys]})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            missing = [f for f in ["company_id", "key_alias", "key_provider", "key_reference", "algorithm"] if not body.get(f)]
            if missing:
                return JsonResponse({"error": f"Missing: {', '.join(missing)}"}, status=400)
            key = KeyManagementService.create_key(
                company_id=body["company_id"], key_alias=body["key_alias"],
                key_provider=body["key_provider"], key_reference=body["key_reference"],
                algorithm=body["algorithm"],
            )
            return JsonResponse({"success": True, "key": _key_to_dict(key)}, status=201)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def key_rotate(request, key_id):
    """POST /keys/<key_id>/rotate/"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        new_key = KeyManagementService.rotate_key(key_id)
        return JsonResponse({"success": True, "new_key": _key_to_dict(new_key)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def key_revoke(request, key_id):
    """POST /keys/<key_id>/revoke/"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        key = KeyManagementService.revoke_key(key_id)
        return JsonResponse({"success": True, "key": _key_to_dict(key)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


def key_active(request, company_id):
    """GET /keys/active/<company_id>/"""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        key = KeyManagementService.get_active_key(company_id)
        if not key:
            return JsonResponse({"error": "No active key for this company"}, status=404)
        return JsonResponse({"key": _key_to_dict(key)})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────
#  DIGITAL SIGNATURE VIEWS
# ─────────────────────────────────────────────────────────────────

def signature_list(request):
    """GET /signatures/?step_id=X&user_id=Y"""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        step_id = request.GET.get("step_id")
        user_id = request.GET.get("user_id")
        sigs = KeyManagementService.list_signatures(
            step_id=int(step_id) if step_id else None,
            user_id=int(user_id) if user_id else None,
        )
        return JsonResponse({"signatures": [_sig_to_dict(s) for s in sigs]})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ─── helpers ──────────────────────────────────

def _step_to_dict(st):
    return {
        "id": st.id, "step_order": st.step_order, "step_name": st.step_name,
        "role_id": st.role_id, "status": st.status,
        "completed_at": st.completed_at.isoformat() if st.completed_at else None,
        "comment": st.approvals.order_by('-id').first().comment if st.approvals.exists() else None,
    }


def _key_to_dict(k):
    return {
        "id": k.id, "company_id": k.company_id, "key_alias": k.key_alias,
        "key_provider": k.key_provider, "key_reference": k.key_reference,
        "algorithm": k.algorithm, "key_version": k.key_version, "status": k.status,
        "created_at": k.created_at.isoformat(),
        "rotated_at": k.rotated_at.isoformat() if k.rotated_at else None,
    }


def _sig_to_dict(s):
    return {
        "id": s.id, "step_id": s.step_id, "user_id": s.user_id,
        "signature_hash": s.signature_hash, "signed_at": s.signed_at.isoformat(),
        "key_id": s.key_id,
        "key_alias": s.key.key_alias if s.key else None,
        "key_algorithm": s.key.algorithm if s.key else None,
        "key_version": s.key.key_version if s.key else None,
    }
