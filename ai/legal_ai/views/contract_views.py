"""legal_ai search entry points over the web's tenant-scoped A3 pipeline."""
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from ai.legal_ai.services import contract_search_service
from .knowledge_views import knowledge_api, json_body


@require_POST
@knowledge_api
def search_contract(request, contract_id):
    return search_response(request.user,contract_id,json_body(request))


def search_response(user, contract_id, data):
    result=contract_search_service.search_contract(user,contract_id,data)
    return JsonResponse(dict(result,search_engine='newidea_a3'))


@require_POST
@knowledge_api
def ask(request):
    """Body-based endpoint for legal_ai clients that already send contract_id."""
    data=json_body(request)
    contract_id=data.get('contract_id')
    if type(contract_id) is not int or contract_id < 1:
        raise ValueError('Chọn hợp đồng trước khi tìm tài liệu A3.')
    return search_response(request.user,contract_id,data)
