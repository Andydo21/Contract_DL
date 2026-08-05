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

from contracts.models import Contract, ContractVersion
from .models import Clause
from .repositories import ContractSummaryRepository, ExtractedEntityRepository
from contracts.repositories import ClauseRepository

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
        Delegates document processing to DocumentService, saves pages to ContractContext,
        and uses Kaggle AI for clause splitting. Falls back to ClauseSplitter if AI fails.
        """
        import os
        import tempfile
        from decimal import Decimal
        from django.conf import settings
        from contracts.crypto_utils import decrypt_pdf
        from contracts.models import ContractContext
        from document_processor.services.document_service import DocumentService
        from document_processor.splitter.clause_splitter import ClauseSplitter

        # 1. Decrypt and run DocumentService if not already parsed or re_extract is True
        contexts_exist = version.contexts.filter(context_type='raw_text').exists()
        if re_extract or not contexts_exist:
            latest_file = version.files.first()
            if not latest_file or not latest_file.file_path:
                raise ValueError("No file available for this contract version.")

            import urllib.parse
            rel_path = urllib.parse.unquote(latest_file.file_path)
            url_prefix = settings.MEDIA_URL
            if rel_path.startswith(url_prefix):
                rel_path = rel_path[len(url_prefix):]
            physical_path = os.path.join(settings.MEDIA_ROOT, rel_path)

            if not os.path.exists(physical_path):
                raise ValueError(f"Contract file does not exist on disk: {physical_path}")

            # Read and decrypt file
            with open(physical_path, 'rb') as f:
                encrypted_bytes = f.read()
            decrypted_bytes = decrypt_pdf(encrypted_bytes)

            # Write to a secure temporary file keeping the original extension
            ext = os.path.splitext(latest_file.file_name)[1].lower() if latest_file.file_name else '.pdf'
            if not ext:
                ext = '.pdf'
                
            temp_dir = tempfile.gettempdir()
            temp_file_name = f"temp_contract_{version.id}_{os.getpid()}{ext}"
            temp_file_path = os.path.join(temp_dir, temp_file_name)

            try:
                with open(temp_file_path, 'wb') as temp_file:
                    temp_file.write(decrypted_bytes)

                # Process file with DocumentService
                service = DocumentService(ocr_lang="vi")
                doc_output = service.process(temp_file_path, split_clauses=False)

                # Clean existing ContractContext for this version to avoid duplicates
                ContractContext.objects.filter(version=version, context_type='raw_text').delete()

                # Save ContractContext (pages)
                for page in doc_output.pages:
                    ContractContext.objects.create(
                        version=version,
                        context_type='raw_text',
                        source=page.source,
                        content=page.text,
                        relevance_score=Decimal(str(round(page.confidence, 2)))
                    )
            finally:
                # Securely delete the temporary decrypted file
                if os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except Exception:
                        pass

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
        url = f"{_kaggle_url()}/api/v1/extract_clauses"
        logger.info(
            f"[clause_extract] POST {url} – version_id={version.id}, text_len={len(raw_text)}"
        )

        ai_clauses = []
        ai_failed = force_rule_based
        if not force_rule_based:
            try:
                resp = requests.post(
                    url,
                    json={"text": raw_text},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                ai_clauses = data.get("clauses", [])
            except requests.RequestException as e:
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