"""NewIdea search entry points over the web's tenant-scoped A3 pipeline."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from NewIdea.services import contract_search_service
from .knowledge_views import knowledge_api, json_body


def workspace(request, contract_id=None):
    from django.contrib.auth.views import redirect_to_login
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    return render_workspace(request, contract_id)


@knowledge_api
def render_workspace(request, contract_id):
    from django.shortcuts import render
    return render(request, 'contracts/intelligence.html',
        contract_search_service.workspace_context(request.user, contract_id, request.GET.get('version_id')))


@require_POST
@knowledge_api
def search_contract(request, contract_id):
    data = contract_search_service.search_contract(request.user, contract_id, json_body(request))
    data['search_engine'] = 'newidea_a3'
    return JsonResponse(data)


@require_POST
def ask(request):
    """Body-based endpoint for NewIdea clients that already send contract_id."""
    if not request.user.is_authenticated:
        return JsonResponse({'success':False,'error':'Authentication required.'},status=401)
    try:
        data=json.loads(request.body)
        contract_id=data.get('contract_id') if isinstance(data,dict) else None
        if type(contract_id) is not int or contract_id < 1:
            raise ValueError('Chọn hợp đồng trước khi tìm tài liệu A3.')
    except (ValueError,TypeError) as error:
        return JsonResponse({'success':False,'error':str(error)},status=400)
    return search_contract(request,contract_id)
