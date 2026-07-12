"""
ai_extract/services.py
======================
Business-logic layer for AI Extract & Summarize.

Calls kaggle_qwen_service (at settings.KAGGLE_QWEN_SERVICE_URL) via HTTP:
  • POST /api/v1/summarize        → saves to ai_extract.ContractSummary
  • POST /api/v1/extract_entities → saves to contracts.ExtractedEntity (same table as rule-based entities)
"""

import logging
import requests
from django.conf import settings

from contracts.models import Contract, ContractVersion, Clause
from .repositories import ContractSummaryRepository, ExtractedEntityRepository

logger = logging.getLogger("ai_extract")

MODEL_ID = "phamthanhfd/contract-analysis-qwen2.5-3b"
REQUEST_TIMEOUT = 300  # 5-minute timeout – model inference can be slow


def _kaggle_url() -> str:
    """Return the base URL of kaggle_qwen_service (no trailing slash)."""
    return getattr(
        settings, "KAGGLE_QWEN_SERVICE_URL", "http://kaggle-qwen-service:8000"
    ).rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Summarize Service
# ─────────────────────────────────────────────────────────────────────────────

class SummarizeService:
    """
    Generate an Executive Summary for a ContractVersion.
    Saves / overwrites ai_extract.ContractSummary in the DB.
    """

    def summarize_version(self, version: ContractVersion) -> dict:
        """
        Calls POST /api/v1/summarize, persists the result.

        Returns:
            {"version_id", "contract_id", "summary", "model_id"}
        """
        clauses = list(version.clauses.all())
        if not clauses:
            raise ValueError(
                f"ContractVersion {version.id} has no clauses. "
                "Run clause extraction first."
            )

        payload = {
            "clauses": [
                {"title": cl.clause_title, "content": cl.clause_content}
                for cl in clauses
            ],
            "contract_metadata": {
                "contract_code": version.contract.contract_code,
                "title": version.contract.title,
                "version": version.version_number,
            },
        }

        url = f"{_kaggle_url()}/api/v1/summarize"
        logger.info(
            f"[summarize] POST {url} – version_id={version.id}, "
            f"{len(clauses)} clauses"
        )

        try:
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"kaggle_qwen_service /api/v1/summarize error: {e}")

        summary_text = data.get("summary", "")

        obj = ContractSummaryRepository.create_or_update(
            version=version,
            summary=summary_text,
            model_id=MODEL_ID,
        )
        logger.info(f"[summarize] Saved ContractSummary id={obj.id}")

        return {
            "version_id": version.id,
            "contract_id": version.contract.id,
            "summary": summary_text,
            "model_id": MODEL_ID,
        }

    def summarize_contract(self, contract_id: int) -> dict:
        """Convenience wrapper – uses the latest version."""
        try:
            contract = Contract.objects.prefetch_related("versions__clauses").get(id=contract_id)
        except Contract.DoesNotExist:
            raise ValueError(f"Contract {contract_id} not found.")

        version = contract.latest_version
        if not version:
            raise ValueError(f"Contract {contract_id} has no version yet.")

        return self.summarize_version(version)


# ─────────────────────────────────────────────────────────────────────────────
# Extract Entity Service
# ─────────────────────────────────────────────────────────────────────────────

class ExtractEntityService:
    """
    Extract structured entities from contract clauses using Kaggle AI and
    save them to contracts.ExtractedEntity (the same table used by rule-based extraction).

    Strategy: one API call per clause (text = [title] + clause_content).
    Results are mapped as:
      COMPANY_NAME  → ExtractedEntity(entity_type="COMPANY_NAME", entity_value=…)
      TAX_CODE      → ExtractedEntity(entity_type="TAX_CODE",      entity_value=…)
      CONTRACT_VALUE→ ExtractedEntity(entity_type="CONTRACT_VALUE", entity_value=…)
      DATE_EFFECTIVE→ ExtractedEntity(entity_type="DATE_EFFECTIVE", entity_value=…)
      DATE_EXPIRE   → ExtractedEntity(entity_type="DATE_EXPIRE",    entity_value=…)
    """

    def extract_version(self, version: ContractVersion, re_extract: bool = False) -> list:
        """
        Run entity extraction for every clause in a ContractVersion.

        Args:
            version:     The ContractVersion to process.
            re_extract:  If True, delete existing Kaggle AI entities first.

        Returns:
            List of dicts with per-clause extraction results.
        """
        if re_extract:
            deleted = ExtractedEntityRepository.delete_kaggle_entities_for_version(version)
            logger.info(f"[extract] Deleted {deleted} existing Kaggle entities for version {version.id}")

        clauses = list(version.clauses.all())
        if not clauses:
            raise ValueError(
                f"ContractVersion {version.id} has no clauses. "
                "Run clause splitting first."
            )

        url = f"{_kaggle_url()}/api/v1/extract_entities"
        results = []

        for clause in clauses:
            text = f"[{clause.clause_title}]\n{clause.clause_content}"
            logger.info(
                f"[extract] POST {url} – clause_id={clause.id} "
                f"'{clause.clause_title[:40]}'"
            )

            try:
                resp = requests.post(
                    url,
                    json={"text": text},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                logger.error(f"[extract] HTTP error for clause {clause.id}: {e}")
                results.append(
                    {
                        "clause_id": clause.id,
                        "clause_title": clause.clause_title,
                        "error": str(e),
                        "entities": {},
                        "saved_count": 0,
                    }
                )
                continue

            raw_entities = data.get("entities", {})

            # Persist into contracts.ExtractedEntity
            saved = ExtractedEntityRepository.save_from_kaggle(
                clause=clause,
                raw_entities=raw_entities,
            )

            logger.info(
                f"[extract] Saved {len(saved)} ExtractedEntity rows "
                f"for clause '{clause.clause_title[:40]}'"
            )

            results.append(
                {
                    "clause_id": clause.id,
                    "clause_title": clause.clause_title,
                    "entities": raw_entities,
                    "saved_count": len(saved),
                    "saved_ids": [e.id for e in saved],
                }
            )

        return results

    def extract_contract(self, contract_id: int, re_extract: bool = False) -> dict:
        """Convenience wrapper – uses the latest version."""
        try:
            contract = Contract.objects.prefetch_related("versions__clauses").get(id=contract_id)
        except Contract.DoesNotExist:
            raise ValueError(f"Contract {contract_id} not found.")

        version = contract.latest_version
        if not version:
            raise ValueError(f"Contract {contract_id} has no version yet.")

        results = self.extract_version(version, re_extract=re_extract)

        return {
            "contract_id": contract.id,
            "version_id": version.id,
            "total_clauses": len(results),
            "results": results,
        }

    def extract_from_text(self, text: str, clause: Clause = None) -> dict:
        """
        Extract entities from arbitrary raw text.
        Optionally persists to ExtractedEntity if a Clause is provided.

        Args:
            text:   Raw text to extract from.
            clause: Optional Clause to persist results against.

        Returns:
            {"entities": {…}, "saved_count": int}
        """
        url = f"{_kaggle_url()}/api/v1/extract_entities"
        logger.info(f"[extract] POST {url} – free-text len={len(text)}")

        try:
            resp = requests.post(url, json={"text": text}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"kaggle_qwen_service /api/v1/extract_entities error: {e}")

        raw_entities = data.get("entities", {})
        saved_count = 0

        if clause:
            saved = ExtractedEntityRepository.save_from_kaggle(
                clause=clause,
                raw_entities=raw_entities,
            )
            saved_count = len(saved)
            logger.info(f"[extract] Saved {saved_count} free-text ExtractedEntity rows")

        return {"entities": raw_entities, "saved_count": saved_count}
