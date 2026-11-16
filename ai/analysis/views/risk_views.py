from contract.core.views.http_results import request_data as _body, service_errors
from contract.core.views.http_results import respond
from ai.analysis.services import risk_service


@service_errors
def api_risks_list(request):
    return respond(request, risk_service.risks_list(method=request.method, data=_body(request)))
