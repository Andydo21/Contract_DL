import hmac
import json
import os
from types import SimpleNamespace
from django.db import connections
from django.http import JsonResponse
from django.urls import resolve


class WorkflowTenantGuard:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/':
            return self.get_response(request)
        from .models import Workflow, WorkflowStep, StepDependency, KeyManagement
        uid = getattr(request, 'jwt_user_id', None)
        trusted = os.getenv('WORKFLOW_SERVICE_TOKEN', '')
        system = uid == 0 and bool(trusted) and hmac.compare_digest(request.headers.get('X-Workflow-Service-Token', ''), trusted)
        if uid is None or (uid == 0 and not system):
            return JsonResponse({'error': 'Authentication required.'}, status=401)
        try:
            match = resolve(request.path)
            name, kw = match.url_name, match.kwargs
            data = json.loads(request.body or '{}') if request.method == 'POST' else {}
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            if system:
                if name not in {'get_workflow', 'get_workflow_by_id_view', 'create_workflow'}:
                    return JsonResponse({'error': 'System token cannot sign or administer users.'}, status=403)
            else:
                with connections['contract_db'].cursor() as c:
                    c.execute('SELECT u.id,u.company_id,u.is_active,u.is_superuser,r.role_name,u.role_id FROM contracts_user u LEFT JOIN contracts_role r ON r.id=u.role_id WHERE u.id=%s', [uid])
                    actor = c.fetchone()
                if not actor or not actor[2] or (not actor[1] and not actor[3]):
                    return JsonResponse({'error': 'Active company account required.'}, status=403)
                manager = actor[3] or (actor[4] or '').upper() in {'ADMIN', 'MANAGER'}
                request.user = SimpleNamespace(id=actor[0], pk=actor[0], company_id=actor[1], role_id=actor[5],
                    role=SimpleNamespace(role_name=actor[4] or 'USER'), is_superuser=actor[3], is_authenticated=True)
                if request.method == 'POST' and name != 'approve_step' and not manager:
                    return JsonResponse({'error': 'Manager permission required.'}, status=403)
                if name == 'approve_step':
                    step = WorkflowStep.objects.get(pk=kw['step_id'])
                    if step.role_id and step.role_id != actor[5] and not actor[3]:
                        return JsonResponse({'error': 'Wrong assigned role.'}, status=403)
                    data.update(user_id=actor[0], company_id=actor[1], is_manager=manager)
                if name.startswith('key_'):
                    data['company_id'] = actor[1]
                request._body = json.dumps(data).encode() if request.method == 'POST' else request.body
                if name in {'key_list_create', 'signature_list'}:
                    query = request.GET.copy()
                    if name == 'key_list_create': query['company_id'] = str(actor[1])
                    else: query['user_id'] = str(actor[0])
                    request.GET = query
                company_id = kw.get('company_id')
                if kw.get('key_id'): company_id = KeyManagement.objects.get(pk=kw['key_id']).company_id
                if company_id and not actor[3] and company_id != actor[1]:
                    return JsonResponse({'error': 'Resource not found.'}, status=404)
            version_id = kw.get('version_id') or data.get('version_id')
            workflow_id = kw.get('workflow_id')
            if kw.get('step_id'): workflow_id = WorkflowStep.objects.get(pk=kw['step_id']).workflow_id
            if kw.get('dependency_id'): workflow_id = StepDependency.objects.get(pk=kw['dependency_id']).workflow_id
            if workflow_id: version_id = Workflow.objects.get(pk=workflow_id).version_id
            if version_id:
                with connections['contract_db'].cursor() as c:
                    c.execute('SELECT c.company_id FROM contracts_contractversion v JOIN contracts_contract c ON c.id=v.contract_id WHERE v.id=%s', [version_id])
                    company = c.fetchone()
                if not company or (not system and not actor[3] and company[0] != actor[1]):
                    return JsonResponse({'error': 'Resource not found.'}, status=404)
            return self.get_response(request)
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid request.'}, status=400)
        except Exception:
            return JsonResponse({'error': 'Authorization unavailable; request denied.'}, status=503)
