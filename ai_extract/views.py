import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from contracts.models import Contract, ContractVersion, Clause
from .services import SummarizeService, ExtractEntityService
from .repositories import ContractSummaryRepository, ExtractedEntityRepository

logger = logging.getLogger("ai_extract")

summarize_svc = SummarizeService()
extract_svc = ExtractEntityService()


def _error(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


# ─────────────────────────────────────────────────────────────────────────────
# Summarize endpoints
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_summarize_contract(request, contract_id: int):
    """
    POST /api/ai/contracts/<contract_id>/summarize/
    Summarize the latest (or specified) version. Result saved to ContractSummary.

    Optional JSON body: { "version_id": <int> }
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        body = {}

    version_id = body.get("version_id")

    try:
        contract = Contract.objects.prefetch_related("versions__clauses").get(id=contract_id)
    except Contract.DoesNotExist:
        return _error(f"Contract {contract_id} not found.", 404)

    if version_id:
        try:
            version = contract.versions.get(id=version_id)
        except ContractVersion.DoesNotExist:
            return _error(f"Version {version_id} not found.", 404)
    else:
        version = contract.latest_version
        if not version:
            return _error("Contract has no version yet.", 400)

    try:
        result = summarize_svc.summarize_version(version)
        return JsonResponse(result, status=200)
    except ValueError as e:
        return _error(str(e), 400)
    except RuntimeError as e:
        logger.exception("Summarize runtime error")
        return _error(str(e), 502)
    except Exception:
        logger.exception("Unexpected error in api_summarize_contract")
        return _error("Internal server error.", 500)


@require_http_methods(["GET"])
def api_get_summary(request, contract_id: int):
    """
    GET /api/ai/contracts/<contract_id>/summary/
    Retrieve the stored ContractSummary for the latest version.
    """
    try:
        contract = Contract.objects.prefetch_related("versions").get(id=contract_id)
    except Contract.DoesNotExist:
        return _error(f"Contract {contract_id} not found.", 404)

    version = contract.latest_version
    if not version:
        return _error("Contract has no version.", 404)

    obj = ContractSummaryRepository.get_by_version(version)
    if not obj:
        return _error("No summary found. Run summarize first.", 404)

    return JsonResponse({
        "id": obj.id,
        "contract_id": contract.id,
        "version_id": version.id,
        "summary": obj.summary,
        "model_id": obj.model_id,
        "created_at": obj.created_at.isoformat(),
        "updated_at": obj.updated_at.isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Extract Entity endpoints
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_extract_entities(request, contract_id: int):
    """
    POST /api/ai/contracts/<contract_id>/extract-entities/
    Run AI entity extraction per clause → saves to contracts.ExtractedEntity.

    Optional JSON body:
      {
        "version_id": <int>,    # default: latest
        "re_extract": true      # delete existing Kaggle entities first
      }
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        body = {}

    version_id = body.get("version_id")
    re_extract = bool(body.get("re_extract", False))

    try:
        contract = Contract.objects.prefetch_related("versions__clauses").get(id=contract_id)
    except Contract.DoesNotExist:
        return _error(f"Contract {contract_id} not found.", 404)

    if version_id:
        try:
            version = contract.versions.get(id=version_id)
        except ContractVersion.DoesNotExist:
            return _error(f"Version {version_id} not found.", 404)
    else:
        version = contract.latest_version
        if not version:
            return _error("Contract has no version yet.", 400)

    try:
        results = extract_svc.extract_version(version, re_extract=re_extract)
        return JsonResponse({
            "contract_id": contract.id,
            "version_id": version.id,
            "total_clauses": len(results),
            "results": results,
        }, status=200)
    except ValueError as e:
        return _error(str(e), 400)
    except RuntimeError as e:
        logger.exception("Extract entities runtime error")
        return _error(str(e), 502)
    except Exception:
        logger.exception("Unexpected error in api_extract_entities")
        return _error("Internal server error.", 500)


@csrf_exempt
@require_http_methods(["POST"])
def api_extract_from_text(request):
    """
    POST /api/ai/extract-from-text/
    Extract entities from arbitrary raw text.

    JSON body:
      {
        "text": "<raw text>",
        "clause_id": <int>   # optional – persist result to this Clause
      }
    """
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _error("Invalid JSON body.", 400)

    text = body.get("text", "").strip()
    if not text:
        return _error("Field 'text' is required.", 400)

    clause_id = body.get("clause_id")
    clause = None
    if clause_id:
        try:
            clause = Clause.objects.get(id=clause_id)
        except Clause.DoesNotExist:
            return _error(f"Clause {clause_id} not found.", 404)

    try:
        result = extract_svc.extract_from_text(text, clause=clause)
        return JsonResponse(result, status=200)
    except RuntimeError as e:
        logger.exception("Extract from text runtime error")
        return _error(str(e), 502)
    except Exception:
        logger.exception("Unexpected error in api_extract_from_text")
        return _error("Internal server error.", 500)


@require_http_methods(["GET"])
def api_get_entities(request, contract_id: int):
    """
    GET /api/ai/contracts/<contract_id>/entities/
    List contracts.ExtractedEntity rows for the latest (or specified) version.
    Includes both AI-extracted and rule-based entities.

    Query params: ?version_id=<int>
    """
    version_id = request.GET.get("version_id")

    try:
        contract = Contract.objects.prefetch_related("versions__clauses").get(id=contract_id)
    except Contract.DoesNotExist:
        return _error(f"Contract {contract_id} not found.", 404)

    if version_id:
        try:
            version = contract.versions.get(id=int(version_id))
        except (ContractVersion.DoesNotExist, ValueError):
            return _error(f"Version {version_id} not found.", 404)
    else:
        version = contract.latest_version
        if not version:
            return _error("Contract has no version.", 404)

    qs = ExtractedEntityRepository.get_by_version(version)

    data = [
        {
            "id": e.id,
            "clause_id": e.clause_id,
            "clause_title": e.clause.clause_title,
            "entity_type": e.entity_type,
            "entity_value": e.entity_value,
            "normalized_value": e.normalized_value,
            "confidence_score": float(e.confidence_score),
        }
        for e in qs
    ]

    return JsonResponse({
        "contract_id": contract.id,
        "version_id": version.id,
        "count": len(data),
        "entities": data,
    })
