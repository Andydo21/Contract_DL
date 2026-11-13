"""Editing a contract's metadata and soft-deleting it through /api/contracts/<id>/."""
import json
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from contracts.models import AuditLog, Company, Contract, ContractVersion, Role


class ContractCrudTests(TestCase):
    def setUp(self):
        # Deleting looks at the extraction job queue, which lives under MEDIA_ROOT: never the real one.
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.company = Company.objects.create(company_name='Tenant')
        manager_role, _ = Role.objects.get_or_create(role_name='MANAGER')
        users = get_user_model().objects
        self.manager = users.create_user(username='manager', password='x', company=self.company, role=manager_role)
        self.staff = users.create_user(username='staff', password='x', company=self.company)
        self.outsider = users.create_user(username='outsider', password='x', role=Role.objects.get_or_create(role_name='ADMIN')[0],
                                          company=Company.objects.create(company_name='Other'))
        self.contract = Contract.objects.create(contract_code='C-1', title='Mua bán', contract_type='',
                                                start_date=date(2026, 1, 1), contract_value=Decimal('100.00'), company=self.company)
        ContractVersion.objects.create(contract=self.contract, version_number=1)
        Contract.objects.create(contract_code='C-2', title='Thuê nhà', company=self.company)
        self.url = f'/api/contracts/{self.contract.pk}/'

    def patch(self, user, body):
        self.client.force_login(user)
        return self.client.patch(self.url, json.dumps(body), content_type='application/json')

    def delete(self, user):
        self.client.force_login(user)
        return self.client.delete(self.url)

    # Update

    def test_manager_updates_metadata_and_the_change_is_audited(self):
        response = self.patch(self.manager, {'title': ' Mua bán hàng hóa ', 'end_date': '2026-12-31', 'contract_value': '2500.5'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['changed'], ['contract_value', 'end_date', 'title'])
        self.contract.refresh_from_db()
        self.assertEqual((self.contract.title, self.contract.end_date, self.contract.contract_value),
                         ('Mua bán hàng hóa', date(2026, 12, 31), Decimal('2500.50')))
        log = AuditLog.objects.get(action__startswith='Updated contract', contract=self.contract)
        self.assertEqual(json.loads(log.payload)['title'], ['Mua bán', 'Mua bán hàng hóa'])

    def test_unchanged_values_are_not_saved_again(self):
        response = self.patch(self.manager, {'title': 'Mua bán', 'contract_type': '', 'contract_value': '100'})
        self.assertEqual(response.json()['changed'], [])
        self.assertFalse(AuditLog.objects.filter(action__startswith='Updated contract').exists())

    def test_invalid_values_are_rejected(self):
        for body in ({'title': '  '}, {'start_date': '01/02/2026'}, {'contract_value': '-1'}, {'contract_value': 'abc'},
                     {'end_date': '2025-12-31'}, {'status': 'APPROVED'}, {'company': 1}):
            with self.subTest(body=body):
                self.assertEqual(self.patch(self.manager, body).status_code, 400)
        self.contract.refresh_from_db()
        self.assertEqual((self.contract.title, self.contract.status), ('Mua bán', 'DRAFT'))

    def test_a_value_too_large_for_the_column_is_rejected(self):
        for value in ('1e30', '9' * 29, '10000000000000000', '9999999999999999.999'):
            with self.subTest(value=value):
                self.assertEqual(self.patch(self.manager, {'contract_value': value}).status_code, 400)
        self.assertEqual(self.patch(self.manager, {'contract_value': '9999999999999999.99'}).status_code, 200)

    def test_a_zero_value_survives_an_edit_of_another_field(self):
        Contract.objects.filter(pk=self.contract.pk).update(contract_value=Decimal('0.00'))
        self.client.force_login(self.manager)
        shown = self.client.get(self.url).json()['contract_value']
        self.assertEqual(shown, 0)
        # The edit form sends back every field as it was shown.
        response = self.patch(self.manager, {'title': 'Mua bán 2', 'contract_value': str(shown)})
        self.assertEqual(response.json()['changed'], ['title'])
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.contract_value, Decimal('0.00'))

    def test_a_change_is_not_saved_without_its_audit_row(self):
        self.client.raise_request_exception = False
        with patch('contracts.repositories.contract_operations_data_repository.log_contract_action', side_effect=RuntimeError('audit down')):
            self.assertEqual(self.patch(self.manager, {'title': 'X'}).status_code, 500)
            self.assertEqual(self.delete(self.manager).status_code, 500)
        self.contract.refresh_from_db()
        self.assertEqual((self.contract.title, self.contract.deleted_at), ('Mua bán', None))

    def test_a_code_already_used_is_rejected(self):
        response = self.patch(self.manager, {'contract_code': 'C-2'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('đã tồn tại', response.json()['error'])

    def test_staff_and_other_companies_cannot_update(self):
        self.assertEqual(self.patch(self.staff, {'title': 'X'}).status_code, 403)
        self.assertEqual(self.patch(self.outsider, {'title': 'X'}).status_code, 403)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.title, 'Mua bán')

    # Soft delete

    def test_delete_hides_the_contract_but_keeps_its_rows(self):
        response = self.delete(self.manager)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Contract.objects.filter(pk=self.contract.pk).exists())
        kept = Contract.all_objects.get(pk=self.contract.pk)
        self.assertIsNotNone(kept.deleted_at)
        self.assertEqual(kept.deleted_by, self.manager)
        self.assertTrue(ContractVersion.objects.filter(contract_id=self.contract.pk).exists())
        # The audit row still points at the deleted contract.
        self.assertTrue(AuditLog.objects.filter(action='Deleted contract: C-1', contract_id=self.contract.pk).exists())

    def test_a_deleted_contract_leaves_the_list_and_cannot_be_opened_or_changed(self):
        self.delete(self.manager)
        listed = self.client.get('/api/contracts/').json()
        self.assertEqual([c['contract_code'] for c in listed], ['C-2'])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.patch(self.manager, {'title': 'X'}).status_code, 404)
        self.assertEqual(self.delete(self.manager).status_code, 404)

    def test_staff_and_other_companies_cannot_delete(self):
        self.assertEqual(self.delete(self.staff).status_code, 403)
        self.assertEqual(self.delete(self.outsider).status_code, 403)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_a_contract_under_analysis_cannot_be_deleted(self):
        Contract.objects.filter(pk=self.contract.pk).update(status='ANALYZING')
        self.assertEqual(self.delete(self.manager).status_code, 409)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_a_deleted_contract_leaves_the_analysis_history_and_cannot_be_reviewed(self):
        from contracts.models import AIAnalysis
        analysis = AIAnalysis.objects.create(version=ContractVersion.objects.get(contract=self.contract), model_name='Qwen',
                                             overall_score=Decimal('10'), summary='ok')
        self.client.force_login(self.manager)
        self.assertEqual([row['contract_code'] for row in self.client.get('/api/analyses/').json()], ['C-1'])
        self.delete(self.manager)
        self.assertEqual(self.client.get('/api/analyses/').json(), [])
        review = self.client.post(f'/api/analyses/{analysis.pk}/review/', json.dumps({'comment': 'ok', 'final_risk_level': 'LOW'}),
                                  content_type='application/json')
        self.assertEqual(review.status_code, 404)
        self.assertEqual(Contract.all_objects.get(pk=self.contract.pk).status, 'DRAFT')

    def test_a_contract_waiting_for_extraction_cannot_be_deleted(self):
        with patch('ai_extract.services.bulk_service.waiting_contract', return_value=True) as waiting:
            response = self.delete(self.manager)
        waiting.assert_called_once_with(self.contract.pk)
        self.assertEqual(response.status_code, 409)
        self.assertIn('trích xuất', response.json()['error'])
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_the_code_of_a_deleted_contract_can_be_used_again(self):
        self.delete(self.manager)
        response = self.client.patch(f'/api/contracts/{Contract.objects.get(contract_code="C-2").pk}/',
                                     json.dumps({'contract_code': 'C-1'}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Contract.all_objects.filter(contract_code='C-1').count(), 2)
        # Two contracts that are both in use still cannot share a code.
        Contract.objects.create(contract_code='C-3', title='Khác', company=self.company)
        self.assertEqual(self.client.patch(f'/api/contracts/{Contract.objects.get(contract_code="C-3").pk}/',
                                           json.dumps({'contract_code': 'C-1'}), content_type='application/json').status_code, 400)

    def test_restore_brings_a_contract_back_unless_its_code_was_taken(self):
        from contracts.repositories import ContractRepository
        self.delete(self.manager)
        deleted = Contract.all_objects.filter(pk=self.contract.pk)
        restored, blocked = ContractRepository.restore_contracts(deleted)
        self.assertEqual(([c.pk for c in restored], blocked), ([self.contract.pk], []))
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

        self.delete(self.manager)
        Contract.objects.create(contract_code='C-1', title='Hợp đồng mới cùng mã', company=self.company)
        restored, blocked = ContractRepository.restore_contracts(deleted)
        self.assertEqual((restored, [c.pk for c in blocked]), ([], [self.contract.pk]))
        self.assertFalse(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_only_managers_get_the_edit_and_delete_buttons(self):
        self.client.force_login(self.manager)
        page = self.client.get(f'/contracts/{self.contract.pk}/').content.decode()
        for marker in ('id="btn-edit-contract"', 'id="btn-delete-contract"', 'id="btn-history-contract"', 'data-code="C-1"',
                       'data-start="2026-01-01"', 'data-value="100.0"', 'contract_actions.js'):
            self.assertIn(marker, page)
        self.assertIn('data-can-manage="1"', self.client.get('/').content.decode())
        self.client.force_login(self.staff)
        page = self.client.get(f'/contracts/{self.contract.pk}/').content.decode()
        self.assertIn('id="btn-history-contract"', page)  # reading the history needs no special role
        for marker in ('btn-edit-contract', 'btn-delete-contract'):
            self.assertNotIn(marker, page)
        dashboard = self.client.get('/').content.decode()
        self.assertIn('data-can-manage=""', dashboard)
        for marker in ('btn-open-trash', 'btn-select-mode', 'bulk-bar'):
            self.assertNotIn(marker, dashboard)

    # Create

    def create(self, **fields):
        self.client.force_login(self.manager)
        return self.client.post('/api/contracts/', dict(dict(contract_code='C-9', title='Dịch vụ'), **fields))

    def test_creating_follows_the_same_rules_as_editing(self):
        for fields in ({'contract_value': '-5'}, {'contract_value': 'abc'}, {'start_date': '2026-05-01', 'end_date': '2026-04-01'},
                       {'start_date': '01/05/2026'}, {'contract_code': 'x' * 51}, {'title': '   '}):
            with self.subTest(fields=fields):
                self.assertEqual(self.create(**fields).status_code, 400)
        self.assertFalse(Contract.objects.filter(contract_code='C-9').exists())
        response = self.create(contract_code=' C-9 ', contract_value='1500.5', start_date='2026-05-01', end_date='2026-12-31')
        self.assertEqual(response.status_code, 200, response.content)
        created = Contract.objects.get(contract_code='C-9')
        self.assertEqual((created.contract_value, created.end_date), (Decimal('1500.50'), date(2026, 12, 31)))
        self.assertTrue(AuditLog.objects.filter(contract=created, action='Created contract: C-9').exists())

    def test_the_list_reports_the_newest_analysis_of_the_latest_version(self):
        from contracts.models import AIAnalysis
        version = ContractVersion.objects.get(contract=self.contract)
        AIAnalysis.objects.create(version=version, model_name='Qwen', overall_score=Decimal('20'), summary='cũ')
        AIAnalysis.objects.create(version=version, model_name='Qwen', overall_score=Decimal('85'), summary='mới')
        self.client.force_login(self.manager)
        rows = {row['contract_code']: row for row in self.client.get('/api/contracts/').json()}
        self.assertEqual((rows['C-1']['risk_score'], rows['C-2']['risk_score']), (85, None))

    # Trash and history

    def test_the_trash_lists_what_the_company_deleted_and_restores_it(self):
        self.delete(self.manager)
        trash = self.client.get('/api/contracts/trash/').json()['contracts']
        self.assertEqual([(row['contract_code'], row['deleted_by'], row['code_taken']) for row in trash], [('C-1', 'manager', False)])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/contracts/trash/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/contracts/{self.contract.pk}/restore/', '{}', content_type='application/json').status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get('/api/contracts/trash/').json()['contracts'], [])
        self.assertEqual(self.client.post(f'/api/contracts/{self.contract.pk}/restore/', '{}', content_type='application/json').status_code, 403)
        self.client.force_login(self.manager)
        response = self.client.post(f'/api/contracts/{self.contract.pk}/restore/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())
        self.assertEqual(self.client.get('/api/contracts/trash/').json()['contracts'], [])
        # Only something deleted can be restored.
        self.assertEqual(self.client.post(f'/api/contracts/{self.contract.pk}/restore/', '{}', content_type='application/json').status_code, 404)

    def test_restoring_a_contract_whose_code_was_taken_needs_a_new_code(self):
        self.delete(self.manager)
        Contract.objects.create(contract_code='C-1', title='Hợp đồng mới cùng mã', company=self.company)
        url = f'/api/contracts/{self.contract.pk}/restore/'
        self.assertTrue(self.client.get('/api/contracts/trash/').json()['contracts'][0]['code_taken'])
        refused = self.client.post(url, '{}', content_type='application/json')
        self.assertEqual((refused.status_code, refused.json()['code_taken']), (409, True))
        self.assertEqual(self.client.post(url, json.dumps({'contract_code': 'C-2'}), content_type='application/json').status_code, 409)
        self.assertEqual(Contract.all_objects.get(pk=self.contract.pk).contract_code, 'C-1')
        self.assertEqual(self.client.post(url, json.dumps({'contract_code': 'C-1-KP'}), content_type='application/json').status_code, 200)
        self.assertEqual(Contract.objects.get(pk=self.contract.pk).contract_code, 'C-1-KP')

    def test_history_shows_who_changed_what_without_the_request_log(self):
        self.patch(self.manager, {'title': 'Mua bán 2', 'contract_value': '250'})
        AuditLog.objects.create(user=self.manager, contract=self.contract, action='Performed PATCH request on /api/contracts/1/',
                                payload='{"title": "raw request body"}')
        AuditLog.objects.create(user=self.staff, contract=self.contract, action=f'Visited page: /contracts/{self.contract.pk}/')
        self.client.force_login(self.staff)
        history = self.client.get(f'/api/contracts/{self.contract.pk}/history/').json()['history']
        self.assertEqual([(row['label'], row['user']) for row in history], [('Sửa thông tin', 'manager')])
        changes = {change['label']: (change['before'], change['after']) for change in history[0]['changes']}
        self.assertEqual(changes, {'Tiêu đề': ('Mua bán', 'Mua bán 2'), 'Giá trị': ('100.00', '250.00')})
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f'/api/contracts/{self.contract.pk}/history/').status_code, 403)

    def test_the_version_still_reaches_its_deleted_contract(self):
        self.delete(self.manager)
        version = ContractVersion.objects.get(contract_id=self.contract.pk)
        self.assertEqual(version.contract.contract_code, 'C-1')
