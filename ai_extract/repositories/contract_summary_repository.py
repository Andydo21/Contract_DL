import hashlib
import urllib.parse
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from cryptography.exceptions import InvalidTag
from django.conf import settings
from django.db.models.functions import MD5
from django.utils import timezone
from contracts.models import ContractContext, ContractVersion
from ai_extract.models import ContractSummary, Clause, ExtractedEntity


class ContractSummaryRepository:
    @staticmethod
    def get_by_version(version: ContractVersion) -> ContractSummary:
        return ContractSummary.objects.filter(version=version).exclude(summary="").first()

    @staticmethod
    def previous_version(version: ContractVersion):
        return version.contract.versions.filter(version_number__lt=version.version_number).order_by("-version_number").first()

    @staticmethod
    def set_fallback(version_id, preliminary):
        """Regex values to show until the model is back; marks the run for retry_summaries."""
        ContractSummary.objects.get_or_create(version_id=version_id)
        # Merged: when a re-run fails, the details of the summary still on screen must survive.
        result = ContractSummaryRepository.stored_result(version_id)
        ContractSummary.objects.filter(version_id=version_id).update(result={**result, "preliminary": preliminary, "retry": True})

    @staticmethod
    def stored_result(version_id):
        row = ContractSummary.objects.filter(version_id=version_id).values("result").first()
        return row["result"] if row else {}

    @staticmethod
    def retryable_version_ids(lost_before):
        """Runs that failed because the model was down, or died with their process."""
        waiting = ContractSummary.objects.filter(run_status="failed", result__retry=True)
        lost = ContractSummary.objects.filter(run_status__in=("queued", "running"), run_status_at__lt=lost_before)
        return list((waiting | lost).values_list("version_id", flat=True))

    @staticmethod
    def _text_rows():
        # The database hashes each row, so checking every version does not transfer the contract text.
        return ContractContext.objects.filter(context_type="raw_text", content__regex=r"\S").annotate(
            digest=MD5("content")).order_by("version_id", "id")

    @staticmethod
    def text_fingerprints(version_ids=None) -> dict:
        """version id -> fingerprint of its text in the database; a version without text is absent."""
        rows = ContractSummaryRepository._text_rows()
        if version_ids is not None:
            rows = rows.filter(version_id__in=version_ids)
        digests = {}
        for version_id, digest in rows.values_list("version_id", "digest"):
            digests.setdefault(version_id, []).append(digest)
        return {version_id: hashlib.sha256("|".join(parts).encode()).hexdigest() for version_id, parts in digests.items()}

    @staticmethod
    def versions_needing_summary(analysis_version="") -> dict:
        """version id -> fingerprint, for text with no summary or a summary out of date with it."""
        fingerprints = ContractSummaryRepository.text_fingerprints()
        rows = {row["version_id"]: row for row in ContractSummary.objects.filter(version_id__in=fingerprints).values(
            "version_id", "summary", "run_status", "source_fingerprint", "analysis_version", "attempted_fingerprint")}
        needed = {}
        for version_id, fingerprint in fingerprints.items():
            row = rows.get(version_id)
            if row is None:
                needed[version_id] = fingerprint
                continue
            if row["run_status"] in ("queued", "running"):
                continue
            # A run refused for this same text (say, an unreadable source) would only be refused again.
            if row["run_status"] == "failed" and row["attempted_fingerprint"] in ("", fingerprint):
                continue
            model_changed = bool(row["analysis_version"] and analysis_version and row["analysis_version"] != analysis_version)
            if not row["summary"] or row["source_fingerprint"] != fingerprint or model_changed:
                needed[version_id] = fingerprint
        return needed

    @staticmethod
    def set_run_status(version_id, state, error=""):
        """Uses update() so a state change does not move updated_at, the time the summary text was generated."""
        if not ContractVersion.objects.filter(pk=version_id).exists():
            return
        ContractSummary.objects.get_or_create(version_id=version_id)
        ContractSummary.objects.filter(version_id=version_id).update(
            run_status=state, run_error=error, run_status_at=timezone.now())

    @staticmethod
    def run_status(version_id):
        return ContractSummary.objects.filter(version_id=version_id).exclude(run_status="").values(
            "run_status", "run_error", "run_status_at").first()

    @staticmethod
    def try_start_run(version_id, lease_seconds, fingerprint="") -> bool:
        """Atomically claim the run; a 'running' state older than the lease belongs to a dead process."""
        ContractSummary.objects.get_or_create(version_id=version_id)
        now = timezone.now()
        return ContractSummary.objects.filter(version_id=version_id).exclude(
            run_status="running", run_status_at__gte=now - timedelta(seconds=lease_seconds),
        ).update(run_status="running", run_error="", run_status_at=now, attempted_fingerprint=fingerprint) == 1

    @staticmethod
    def create_or_update(version: ContractVersion, summary: str, model_id: str = "", result=None, fingerprint="", analysis_version="") -> ContractSummary:
        obj, _ = ContractSummary.objects.update_or_create(
            version=version,
            defaults={
                "summary": summary,
                **({"model_id": model_id} if model_id else {}),
                **({"result": result} if result is not None else {}),
                "source_fingerprint": fingerprint,
                "analysis_version": analysis_version,
            },
        )
        return obj

    @staticmethod
    def version_by_id(version_id) -> ContractVersion:
        return ContractVersion.objects.select_related("contract").get(pk=version_id)

    @staticmethod
    def versions_of(contract):
        return contract.versions.order_by("version_number")

    @staticmethod
    def latest_file(version: ContractVersion):
        return version.files.order_by("-id").first()

    @staticmethod
    def display_name(record):
        """File names are stored from the media URL, so Vietnamese names arrive percent-encoded."""
        return urllib.parse.unquote(record.file_name) if record and record.file_name else None

    @staticmethod
    def stored_text(version: ContractVersion) -> str:
        """The contract text kept in the database (one raw_text row per page or per manual entry)."""
        rows = version.contexts.filter(context_type="raw_text").order_by("id").values_list("content", flat=True)
        return "\n\n".join(row.strip() for row in rows if row and row.strip())

    @staticmethod
    def source_file(version: ContractVersion):
        """What to summarize: {'name', 'data', 'origin'}. The text in the database comes first and goes to
        ai_summary as a plain text file; the decrypted upload is the fallback. None when there is neither.
        """
        # Taken before the text: if the text changes in between, the summary correctly shows as out of date.
        fingerprint = ContractSummaryRepository.text_fingerprints([version.id]).get(version.id)
        text = ContractSummaryRepository.stored_text(version)
        if text:
            return {"name": "contract_text.txt", "data": text.encode("utf-8"), "origin": "database", "fingerprint": fingerprint}
        record = ContractSummaryRepository.latest_file(version)
        if not record or not record.file_path:
            return None
        from contracts.services.document_encryption_service import decrypt_pdf
        root = Path(settings.MEDIA_ROOT).resolve()
        relative = urllib.parse.unquote(record.file_path).lstrip("/\\")
        prefix = settings.MEDIA_URL.strip("/\\")
        if prefix and relative.startswith(f"{prefix}/"):
            relative = relative[len(prefix) + 1:]
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Đường dẫn file nằm ngoài kho hợp đồng.")
        try:
            data = decrypt_pdf(path.read_bytes())
        except (OSError, InvalidTag, ValueError) as error:
            raise ValueError(f"Không đọc/giải mã được file {ContractSummaryRepository.display_name(record) or path.name}.") from error
        return {"name": ContractSummaryRepository.display_name(record) or path.name, "data": data, "origin": "file",
                "fingerprint": f"file:{record.id}"}

    @staticmethod
    def get_all():
        return (
            ContractSummary.objects.select_related(
                "version__contract"
            ).order_by("-created_at")
        )
