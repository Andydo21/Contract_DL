import urllib.parse
from pathlib import Path

from contract.contracts.models import ContractFile


class ContractFileRepository:
    @staticmethod
    def create_file_record(version, file_path):
        """file_path is the storage URL (percent-encoded); the file name is kept readable, e.g. "Hợp_đồng.pdf"."""
        file_name = Path(urllib.parse.unquote(file_path)).name
        return ContractFile.objects.create(version=version, file_name=file_name, file_path=file_path)
