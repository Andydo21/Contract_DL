from django.urls import path
from contract.approvals.views import workflow_proxy, workflow_views


def proxy(target):
    """A route answered by workflow-service, reached through the web's own domain."""
    return lambda request, **kwargs: workflow_proxy.proxy_to_workflow(request, target.format(**kwargs))


urlpatterns = [
    path('workflows/', workflow_views.workflow_board, name='workflow_board'),
    path('api/contracts/<int:contract_id>/workflow/', workflow_views.api_push_to_workflow, name='api_push_to_workflow'),
    path('api/contracts/<int:contract_id>/workflow/status/', workflow_views.api_workflow_status, name='api_workflow_status'),
    # Workflow Service Reverse Proxy (enables seamless single-domain online access)
    path('board/', workflow_proxy.proxy_to_workflow, {'path': 'board/'}, name='workflow_board_proxy'),
    path('board/<path:path>', proxy('board/{path}')),
    path('workflows/detail/<int:workflow_id>/', proxy('workflows/detail/{workflow_id}/')),
    path('workflows/steps/<int:step_id>/approve/', proxy('workflows/steps/{step_id}/approve/')),
    path('workflows/steps/<int:step_id>/<path:path>', proxy('workflows/steps/{step_id}/{path}')),
    path('workflows/<int:workflow_id>/<path:path>', proxy('workflows/{workflow_id}/{path}')),
    path('workflows/<path:path>', proxy('workflows/{path}')),
    path('dependencies/<path:path>', proxy('dependencies/{path}')),
    # Signing keys live in workflow_service; the admin dashboard manages them through these paths.
    path('api/admin/keys/', proxy('keys/'), name='admin_keys_proxy'),
    path('api/admin/keys/<int:key_id>/rotate/', proxy('keys/{key_id}/rotate/')),
    path('api/admin/keys/<int:key_id>/revoke/', proxy('keys/{key_id}/revoke/')),
]
