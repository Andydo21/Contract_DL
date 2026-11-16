"""A file whose name has Vietnamese letters is stored under a percent-encoded URL; every reader must still find it."""
import hashlib
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from contract.contracts.models import Company, Contract, ContractFile, ContractVersion
from contract.contracts.repositories.contract_file_repository import ContractFileRepository
from blockchain.ledger.services import ledger_service
from contract.contracts.services.contract_operations_service import _remove_stored_files
from contract.contracts.services.contract_service import _store_document
from contract.contracts.services.document_download_service import download_file
from contract.core.services.stored_file_service import document_text, physical_path


class Upload:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def read(self):
        return self.data


class VietnameseFileNameTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = override_settings(MEDIA_ROOT=temp.name, MEDIA_URL='/media/')
        settings.enable()
        self.addCleanup(settings.disable)
        company = Company.objects.create(company_name='A', tax_code='A')
        self.user = type('U', (), dict(is_authenticated=True, is_superuser=True, company_id=company.pk))()
        contract = Contract.objects.create(company=company, contract_code='HD-01', title='Hợp đồng mua bán')
        self.version = ContractVersion.objects.create(contract=contract, version_number=1)
        self.raw = b'%PDF-1.7 original bytes'
        url = _store_document(Upload('Hợp đồng mua bán.pdf', self.raw), None, 'unused.txt')
        self.file = ContractFileRepository.create_file_record(self.version, url)

    def test_the_url_is_percent_encoded_but_the_name_stays_readable(self):
        self.assertIn('%', self.file.file_path)
        self.assertEqual(self.file.file_name, 'Hợp đồng mua bán.pdf')
        self.assertTrue(physical_path(self.file.file_path).is_file())

    def test_signing_reads_the_original_file(self):
        self.assertEqual(ledger_service.snapshot(self.version)['document_hash'], hashlib.sha256(self.raw).hexdigest())

    def test_download_returns_the_uploaded_file_under_its_name(self):
        response = download_file(self.file.pk, self.user, 'application/json')
        self.assertEqual(response.payload, self.raw)
        self.assertIn("filename*=utf-8''H%E1%BB%A3p%20%C4%91%E1%BB%93ng%20mua%20b%C3%A1n.pdf",
                      response.headers['Content-Disposition'])

    def test_deleting_removes_the_file_from_disk(self):
        path = physical_path(self.file.file_path)
        self.assertEqual(_remove_stored_files([self.file.file_path], []), 1)
        self.assertFalse(path.exists())

    def test_a_pasted_text_is_read_back_as_text(self):
        url = _store_document(None, 'Điều 1. Nội dung', 'contract_HD-01.txt')
        stored = ContractFile.objects.create(version=self.version, file_path=url, file_name=Path(url).name)
        self.assertEqual(document_text(stored), 'Điều 1. Nội dung')

    def test_a_path_outside_the_media_folder_is_refused(self):
        self.assertIsNone(physical_path('/media/../../etc/passwd'))
