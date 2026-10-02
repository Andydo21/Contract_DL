"""
ai_extract/services.py
======================
Business-logic layer for AI Extract & Summarize.

Uses the notebook's OpenAI-compatible /v1/chat/completions API, with a
legacy fallback for the former /api/v1/* service.
"""

import logging

from contracts.models import Contract, ContractVersion
from .models import Clause
from .repositories import ContractSummaryRepository, ExtractedEntityRepository
from contracts.repositories import ClauseRepository
from .qwen_client import request_qwen

logger = logging.getLogger("ai_extract")

MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"


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
        clauses = list(Clause.objects.filter(version=version))
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

        logger.info(
            f"[summarize] Qwen chat completion – version_id={version.id}, "
            f"{len(clauses)} clauses"
        )

        try:
            data = request_qwen("summarize", payload)
        except RuntimeError as e:
            raise RuntimeError(f"Qwen summarize error: {e}") from e

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
            contract = Contract.objects.prefetch_related("versions__ai_extract_clauses").get(id=contract_id)
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

        clauses = list(Clause.objects.filter(version=version))
        if not clauses:
            logger.info(f"[extract] No clauses found for version {version.id}. Running ClauseExtractService first.")
            from .services import ClauseExtractService
            clause_extractor = ClauseExtractService()
            clause_extractor.extract_version(version, re_extract=True)
            clauses = list(Clause.objects.filter(version=version))
            if not clauses:
                raise ValueError(
                    f"ContractVersion {version.id} has no clauses after splitting."
                )

        results = []

        for clause in clauses:
            text = f"[{clause.clause_title}]\n{clause.clause_content}"
            logger.info(
                f"[extract] Qwen chat completion – clause_id={clause.id} "
                f"'{clause.clause_title[:40]}'"
            )

            try:
                data = request_qwen("extract_entities", {"text": text})
            except RuntimeError as e:
                logger.error(f"[extract] HTTP error for clause {clause.id}: {e}")
                raise RuntimeError(f"Không thể kết nối đến máy chủ AI (AI Service communication failed): {e}")

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
            contract = Contract.objects.prefetch_related("versions__ai_extract_clauses").get(id=contract_id)
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
        logger.info(f"[extract] Qwen chat completion – free-text len={len(text)}")

        try:
            data = request_qwen("extract_entities", {"text": text})
        except RuntimeError as e:
            raise RuntimeError(f"Qwen extract_entities error: {e}") from e

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





# ─────────────────────────────────────────────────────────────────────────────
# Clause Extract Service
# ─────────────────────────────────────────────────────────────────────────────

class ClauseExtractService:
    """
    Extract and split contract clauses from raw text using Kaggle AI,
    then save them to contracts.Clause (same table used by rule-based splitting).

    Strategy: send the full raw text of a ContractVersion to the AI, which
    returns a JSON list of {title, content, clause_type} objects.
    Existing clauses for the version are optionally deleted before re-saving.
    """

    def extract_version(self, version: ContractVersion, re_extract: bool = False, force_rule_based: bool = False) -> dict:
        """
        Run AI clause extraction for a ContractVersion.
        Delegates document processing to the PlanA vision pipeline, saves pages to ContractContext,
        and uses Kaggle AI for clause splitting. Falls back to ClauseSplitter if AI fails.
        """
        from document_processor.splitter.clause_splitter import ClauseSplitter
        from .layout_service import LayoutExtractionService

        # 1. Decrypt and run PlanA page-layout extraction when needed.
        contexts_exist = version.contexts.filter(context_type='raw_text').exists()
        if re_extract or not contexts_exist:
            has_file = version.files.exclude(file_path="").exists()
            if has_file:
                LayoutExtractionService().extract_version(version)
            elif not (contexts_exist or version.ai_extract_clauses.exists()):
                raise ValueError("No file available for this contract version.")

        # 2. Gather raw text from contexts
        raw_text = self._get_raw_text(version)
        if not raw_text:
            raise ValueError(
                f"ContractVersion {version.id} has no raw text available."
            )

        if re_extract:
            # Delete existing clauses (cascade deletes entities if mapped)
            version.ai_extract_clauses.all().delete()

        # 3. Call AI Clause Splitting Service
        logger.info(
            f"[clause_extract] Qwen chat completion – version_id={version.id}, text_len={len(raw_text)}"
        )

        ai_clauses = []
        ai_failed = force_rule_based
        if not force_rule_based:
            try:
                data = request_qwen("extract_clauses", {"text": raw_text})
                ai_clauses = data.get("clauses", [])
            except RuntimeError as e:
                logger.warning(f"[clause_extract] AI clause splitting failed, falling back to rule-based splitter: {e}")
                ai_failed = True
        else:
            logger.info("[clause_extract] Force rule-based extraction requested.")

        saved_clauses = []
        clause_repo = ClauseRepository()

        if ai_clauses and not ai_failed:
            # AI extracted successfully
            for item in ai_clauses:
                title = (item.get("title") or "").strip()
                content = (item.get("content") or "").strip()
                clause_type = (item.get("clause_type") or "").strip() or None

                if not title or not content:
                    continue

                clause = clause_repo.create_clause(version, title, content)
                if clause_type:
                    clause.clause_type = clause_type
                    clause.save(update_fields=["clause_type"])

                saved_clauses.append({
                    "clause_id": clause.id,
                    "clause_title": clause.clause_title,
                    "clause_type": clause.clause_type,
                    "content_length": len(clause.clause_content),
                })
            logger.info(f"[clause_extract] Saved {len(saved_clauses)} AI-extracted Clause rows.")

        # If AI failed or returned no valid clauses, fall back to rule-based ClauseSplitter!
        if not saved_clauses:
            logger.info("[clause_extract] AI returned no clauses or failed. Using rule-based ClauseSplitter fallback.")
            contexts = version.contexts.filter(context_type="raw_text").order_by("id")
            from document_processor.models.page import PageData
            pages = []
            for i, c in enumerate(contexts):
                pages.append(PageData(
                    page_number=i + 1,
                    text=c.content,
                    source=c.source,
                    confidence=float(c.relevance_score)
                ))
            
            splitter = ClauseSplitter()
            split_results = splitter.split(pages)
            for item in split_results:
                clause = clause_repo.create_clause(version, item.title, item.content)
                saved_clauses.append({
                    "clause_id": clause.id,
                    "clause_title": clause.clause_title,
                    "clause_type": getattr(clause, 'clause_type', None),
                    "content_length": len(clause.clause_content),
                })
            logger.info(f"[clause_extract] Saved {len(saved_clauses)} Rule-based fallback Clause rows.")

        return {
            "version_id": version.id,
            "contract_id": version.contract.id,
            "total_clauses": len(saved_clauses),
            "clauses": saved_clauses,
        }

    def extract_contract(self, contract_id: int, re_extract: bool = False) -> dict:
        """Convenience wrapper – uses the latest version."""
        try:
            contract = Contract.objects.prefetch_related("versions__ai_extract_clauses").get(
                id=contract_id
            )
        except Contract.DoesNotExist:
            raise ValueError(f"Contract {contract_id} not found.")

        version = contract.latest_version
        if not version:
            raise ValueError(f"Contract {contract_id} has no version yet.")

        return self.extract_version(version, re_extract=re_extract)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _get_raw_text(version: ContractVersion) -> str:
        """
        Reconstruct raw contract text for the version.
        Priority:
          1. Concatenate ContractContext.content rows (context_type="raw_text")
          2. Fall back to joining existing clause title + content
        """
        # 1. Try ContractContext with context_type="raw_text"
        contexts = version.contexts.filter(context_type="raw_text").order_by("id")
        if contexts.exists():
            return "\n\n".join(c.content for c in contexts)

        # 2. Fall back to reconstructing from existing clauses
        clauses = list(version.ai_extract_clauses.all())
        if clauses:
            return "\n\n".join(
                f"{cl.clause_title}\n{cl.clause_content}" for cl in clauses
            )

        return ""
