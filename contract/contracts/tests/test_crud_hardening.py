"""Contract CRUD: codes per company, atomic creation, version numbering, upload checks, the detail and list reads."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from contract.contracts.models import AuditLog, Company, Contract, ContractFile, ContractVersion, Role

PDF = b'%PDF-1.4\n%test\n'


class CrudHardeningTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        override = override_settings(MEDIA_ROOT=media.name, AI_SUMMARY_AUTO=False)
        override.enable()
        self.addCleanup(override.disable)
        role, _ = Role.objects.get_or_create(role_name='MANAGER')
        users = get_user_model().objects
        self.company, self.other = Company.objects.create(company_name='A'), Company.objects.create(company_name='B')
        self.manager = users.create_user('m_a', password='x', company=self.company, role=role)
        self.other_manager = users.create_user('m_b', password='x', company=self.other, role=role)
        self.client.force_login(self.manager)

    def create(self, code, **extra):
        return self.client.post('/api/contracts/', dict(contract_code=code, title='Hợp đồng', **extra))

    def stored_files(self):
        root = self.media / 'contract' / 'contracts'
        return sorted(p.name for p in root.iterdir()) if root.exists() else []

    # Codes

    def test_a_code_is_unique_per_company_only(self):
        self.assertEqual(self.create('HD-1', raw_content='Điều 1').status_code, 200)
        duplicate = self.create('HD-1', raw_content='Điều 1')
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('đã tồn tại', duplicate.json()['error'])
        self.client.force_login(self.other_manager)
        self.assertEqual(self.create('HD-1', raw_content='Điều 1').status_code, 200, 'another company may use the same code')
        self.assertEqual(Contract.objects.filter(contract_code='HD-1').count(), 2)

    def test_the_trash_only_reports_a_code_taken_inside_the_same_company(self):
        mine = Contract.objects.create(contract_code='T-1', title='x', company=self.company)
        self.client.delete(f'/api/contracts/{mine.pk}/')
        Contract.objects.create(contract_code='T-1', title='y', company=self.other)
        rows = self.client.get('/api/contracts/trash/').json()['contracts']
        self.assertEqual([(r['contract_code'], r['code_taken']) for r in rows], [('T-1', False)])
        self.assertEqual(self.client.post(f'/api/contracts/{mine.pk}/restore/', '{}', content_type='application/json').status_code, 200)

    # Creating

    def test_creation_leaves_nothing_behind_when_a_later_step_fails(self):
        with patch('contract.contracts.repositories.contract_operations_data_repository.log_contract_action',
                   side_effect=RuntimeError('db password=secret')):
            response = self.create('R-1', file=SimpleUploadedFile('hd.pdf', PDF))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secret', response.json()['error'], 'internal errors are not sent to the browser')
        self.assertFalse(Contract.all_objects.filter(contract_code='R-1').exists())
        self.assertFalse(ContractVersion.objects.filter(contract__contract_code='R-1').exists())
        self.assertEqual(self.stored_files(), [], 'the encrypted upload is removed with the rolled-back rows')

    def test_the_upload_hash_is_recorded_on_the_version(self):
        import hashlib
        self.assertEqual(self.create('H-1', file=SimpleUploadedFile('hd.pdf', PDF)).status_code, 200)
        version = ContractVersion.objects.get(contract__contract_code='H-1')
        self.assertEqual(version.file_hash, hashlib.sha256(PDF).hexdigest())

    def test_uploads_must_be_what_their_name_says_and_within_the_size_limit(self):
        for upload, message in ((SimpleUploadedFile('virus.exe', b'MZ'), 'Không nhận loại file'),
                                (SimpleUploadedFile('fake.pdf', b'hello'), 'không phải PDF'),
                                (SimpleUploadedFile('fake.docx', b'hello'), 'không phải DOCX'),
                                (SimpleUploadedFile('empty.txt', b''), 'rỗng')):
            response = self.create('U-1', file=upload)
            self.assertEqual(response.status_code, 400, upload.name)
            self.assertIn(message, response.json()['error'])
        with override_settings(CONTRACT_UPLOAD_MAX_MB=0):
            self.assertIn('vượt quá', self.create('U-1', file=SimpleUploadedFile('hd.pdf', PDF)).json()['error'])
        self.assertFalse(Contract.objects.filter(contract_code='U-1').exists())
        self.assertEqual(self.create('U-1', file=SimpleUploadedFile('hd.txt', 'Điều 1'.encode())).status_code, 200)

    # Versions

    def test_versions_are_numbered_after_the_highest_and_a_number_cannot_repeat(self):
        contract = Contract.objects.create(contract_code='V-1', title='x', company=self.company)
        ContractVersion.objects.create(contract=contract, version_number=1)
        ContractVersion.objects.create(contract=contract, version_number=3)  # a gap, e.g. after a purge
        response = self.client.post(f'/api/contracts/{contract.pk}/versions/', {'raw_content': 'Điều 1 sửa', 'change_summary': 'sửa'})
        self.assertEqual(response.json()['version_number'], 4, response.content)
        self.assertTrue(AuditLog.objects.filter(contract=contract, action='Added version: v4').exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContractVersion.objects.create(contract=contract, version_number=4)

    def test_a_failed_version_upload_adds_no_version(self):
        contract = Contract.objects.create(contract_code='V-2', title='x', company=self.company)
        ContractVersion.objects.create(contract=contract, version_number=1)
        with patch('contract.contracts.repositories.contract_operations_data_repository.log_contract_action',
                   side_effect=RuntimeError('boom')):
            response = self.client.post(f'/api/contracts/{contract.pk}/versions/', {'file': SimpleUploadedFile('v2.pdf', PDF)})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(list(contract.versions.values_list('version_number', flat=True)), [1])
        self.assertEqual(self.stored_files(), [])

    def test_the_version_list_does_not_build_the_whole_detail_page(self):
        contract = Contract.objects.create(contract_code='V-3', title='x', company=self.company)
        ContractVersion.objects.create(contract=contract, version_number=1)
        with patch('contract.approvals.services.workflow_service.WorkflowService.get_workflow_status') as workflow:
            response = self.client.get(f'/api/contracts/{contract.pk}/versions/')
        self.assertEqual([v['version_number'] for v in response.json()['versions']], [1])
        workflow.assert_not_called()

    # Detail

    def test_an_unknown_version_is_not_found_instead_of_another_version(self):
        contract = Contract.objects.create(contract_code='D-1', title='x', company=self.company)
        ContractVersion.objects.create(contract=contract, version_number=1)
        other = Contract.objects.create(contract_code='D-2', title='y', company=self.company)
        foreign_version = ContractVersion.objects.create(contract=other, version_number=1)
        for version_id in (foreign_version.pk, 999999, 'abc'):
            self.assertEqual(self.client.get(f'/api/contracts/{contract.pk}/?version_id={version_id}').status_code, 404, version_id)

    def test_opening_a_contract_without_versions_writes_nothing(self):
        contract = Contract.objects.create(contract_code='D-3', title='x', company=self.company)
        response = self.client.get(f'/api/contracts/{contract.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['active_version_id'])
        self.assertFalse(contract.versions.exists())

    def test_the_detail_query_count_does_not_grow_with_clauses_or_versions(self):
        from ai.ai_extract.models import Clause, ExtractedEntity
        contract = Contract.objects.create(contract_code='D-4', title='x', company=self.company)

        def add_version(number, clauses):
            version = ContractVersion.objects.create(contract=contract, version_number=number)
            for i in range(clauses):
                clause = Clause.objects.create(version=version, clause_title=f'Điều {i}', clause_content='...')
                ExtractedEntity.objects.create(clause=clause, entity_type='MONEY', entity_value='1')
                ExtractedEntity.objects.create(clause=clause, entity_type='DATE', entity_value='2')

        def queries():
            with patch('contract.approvals.services.workflow_service.WorkflowService.get_workflow_status', return_value=None), \
                    CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(f'/api/contracts/{contract.pk}/').status_code, 200)
            return len(captured)

        add_version(1, 2)
        small = queries()
        add_version(2, 12)
        add_version(3, 12)
        self.assertEqual(queries(), small)

    # List

    def test_the_list_can_be_paged_and_searched(self):
        for i in range(5):
            Contract.objects.create(contract_code=f'L-{i}', title='Thuê kho' if i % 2 else 'Mua bán', company=self.company,
                                    status='APPROVED' if i == 4 else 'DRAFT')
        Contract.objects.create(contract_code='L-X', title='Thuê kho', company=self.other)
        self.assertEqual(len(self.client.get('/api/contracts/').json()), 5, 'without limit the whole list, as before')
        page = self.client.get('/api/contracts/?limit=2&offset=1').json()
        self.assertEqual((page['total'], len(page['items']), page['offset']), (5, 2, 1))
        found = self.client.get('/api/contracts/?limit=10&q=thuê').json()
        self.assertEqual(sorted(c['contract_code'] for c in found['items']), ['L-1', 'L-3'])
        self.assertEqual([c['contract_code'] for c in self.client.get('/api/contracts/?limit=10&status=approved').json()['items']], ['L-4'])
        self.assertEqual(self.client.get('/api/contracts/?limit=x').status_code, 400)

    def test_methods_an_endpoint_does_not_take_are_refused(self):
        self.assertEqual(self.client.post('/api/contracts/trash/').status_code, 405)
        self.assertEqual(self.client.get(f'/api/contracts/1/restore/').status_code, 405)
