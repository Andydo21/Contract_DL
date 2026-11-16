"""Deleting a contract: managers of its company only; postponed only while ledger work is still in flight (a
background extraction of it is cancelled instead, and other documents' extraction goes on);
the graph and vectors go first, workflows and the local ledger copy go with it, the audit trail stays."""
import json
import tempfile
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from contract.contracts.ledger_models import ContractLedgerOperation
from contract.contracts.models import AIAnalysis, AuditLog, Company, Contract, ContractFile, ContractVersion, KnowledgeSearchLog, Role, User
from contract.contracts.services import contract_operations_service as ops

MEDIA = tempfile.mkdtemp()
PURGED = dict(graph=dict(deleted_nodes=3), vectors={'a3_dense': 'deleted'})


def outcome(value):
    return dict(side_effect=value) if isinstance(value, Exception) else dict(return_value=value)


@override_settings(MEDIA_ROOT=MEDIA, MEDIA_URL='/media/')
class DeleteContractTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Công ty A', tax_code='0101010101')
        self.manager = User.objects.create_user('manager', password='x', company=self.company,
                                                role=Role.objects.create(role_name='MANAGER'))
        self.staff = User.objects.create_user('staff', password='x', company=self.company,
                                              role=Role.objects.create(role_name='STAFF'))
        self.contract = Contract.objects.create(contract_code='HD-01', title='Hợp đồng thuê', company=self.company)
        self.version = ContractVersion.objects.create(contract=self.contract, version_number=1)
        stored = Path(MEDIA) / 'contracts' / 'hd01.pdf'
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(b'%PDF')
        self.stored = stored
        ContractFile.objects.create(version=self.version, file_path='/media/contracts/hd01.pdf')
        AIAnalysis.objects.create(version=self.version, model_name='qwen', overall_score=40)
        AuditLog.objects.create(user=self.manager, contract=self.contract, action='CREATE_CONTRACT')
        KnowledgeSearchLog.objects.create(user=self.staff, version=self.version, query='phạt vi phạm?')

    def services(self, stack, workflows=0, purge=PURGED, waiting=False):
        self.cancel = stack.enter_context(patch('ai.ai_extract.services.bulk_service.cancel_contract', return_value=waiting))
        deleted = stack.enter_context(patch('contract.approvals.services.workflow_service.WorkflowService.delete_workflows',
                                            **outcome(workflows)))
        purged = stack.enter_context(patch('ai.ai_extract.services.layout_service.purge_contract_index', **outcome(purge)))
        return deleted, purged

    def delete(self, user, **services):
        with ExitStack() as stack:
            deleted, purged = self.services(stack, **services)
            return ops.contract_detail(self.contract.pk, user=user, method='DELETE', query={}), purged

    def anchored(self, **changes):
        now = timezone.now()
        fields = dict(version=self.version, company=self.company, actor=self.manager, kind='ANCHOR', idempotency_key='k' * 64,
                      manifest='{}', state='CONFIRMED', accepted_at=now, expires_at=now + timedelta(days=1),
                      next_attempt_at=now, tx_id='t' * 64, block_number=9, confirmed_at=now, booked_at=now)
        fields.update(changes)
        return ContractLedgerOperation.objects.create(**fields)

    def test_a_manager_deletes_the_contract_with_its_files_index_and_search_history(self):
        result, purged = self.delete(self.manager)
        self.assertEqual(result.status, 200, result.payload)
        purged.assert_called_once()
        self.assertFalse(Contract.objects.filter(pk=self.contract.pk).exists())
        self.assertFalse(ContractVersion.objects.filter(pk=self.version.pk).exists())
        self.assertFalse(AIAnalysis.objects.exists())
        self.assertFalse(KnowledgeSearchLog.objects.exists())
        self.assertFalse(self.stored.exists())
        self.assertEqual(result.payload['removed_files'], 1)

    def test_the_audit_trail_outlives_the_contract(self):
        self.delete(self.manager)
        record = AuditLog.objects.get(action='DELETE_CONTRACT')
        self.assertEqual((record.user, record.contract, json.loads(record.payload)['contract_code']), (self.manager, None, 'HD-01'))
        self.assertTrue(AuditLog.objects.get(action='CREATE_CONTRACT').payload.startswith('[contract HD-01]'))

    def test_a_contract_signed_on_the_ledger_is_deleted_and_its_transactions_are_kept_in_the_audit(self):
        self.anchored()
        result, _ = self.delete(self.manager, workflows=1)
        self.assertEqual(result.status, 200, result.payload)
        self.assertFalse(ContractLedgerOperation.objects.exists())
        audit = json.loads(AuditLog.objects.get(action='DELETE_CONTRACT').payload)
        evidence = audit['ledger_evidence'][0]
        self.assertEqual((evidence['tx_id'], evidence['block_number'], audit['workflows']), ('t' * 64, 9, 1))

    def test_a_transaction_not_yet_in_the_ledger_book_postpones_deletion(self):
        self.anchored(booked_at=None)
        result, purged = self.delete(self.manager)
        self.assertEqual((result.status, result.payload['code']), (409, 'delete_blocked'))
        purged.assert_not_called()

    def test_a_signed_operation_waiting_for_the_worker_postpones_deletion(self):
        self.anchored(state='PENDING', tx_id=None, booked_at=None)
        self.assertEqual(self.delete(self.manager)[0].status, 409)

    def test_a_prepared_but_never_signed_operation_does_not_block(self):
        self.anchored(state='PENDING', accepted_at=None, tx_id=None, booked_at=None)
        self.assertEqual(self.delete(self.manager)[0].status, 200)

    def test_its_workflows_are_deleted_with_it(self):
        with ExitStack() as stack:
            deleted, _ = self.services(stack, workflows=2)
            result = ops.delete_contract(self.contract.pk, self.manager)
        self.assertEqual(result.payload['workflows_deleted'], 2)
        deleted.assert_called_once_with([self.version.pk])

    def test_an_unreachable_workflow_service_keeps_the_contract(self):
        result, _ = self.delete(self.manager, workflows=RuntimeError('down'))
        self.assertEqual(result.status, 502)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_staff_cannot_delete(self):
        result, purged = self.delete(self.staff)
        self.assertEqual(result.status, 403)
        purged.assert_not_called()
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_a_manager_of_another_company_cannot_delete(self):
        other = User.objects.create_user('other', password='x', role=self.manager.role,
                                         company=Company.objects.create(company_name='Công ty B', tax_code='0202020202'))
        self.assertEqual(self.delete(other)[0].status, 403)

    def test_a_background_extraction_does_not_postpone_deletion_it_is_cancelled(self):
        self.contract.status = 'ANALYZING'
        self.contract.save()
        result, purged = self.delete(self.manager, waiting=True)
        self.assertEqual(result.status, 200)
        self.cancel.assert_called_once_with(self.contract.pk)
        self.assertTrue(result.payload['background_extraction_cancelled'])
        purged.assert_called_once()
        self.assertFalse(Contract.objects.filter(pk=self.contract.pk).exists())

    def test_a_failed_index_purge_keeps_the_contract(self):
        result, _ = self.delete(self.manager, purge=ConnectionError('qdrant down'))
        self.assertEqual(result.status, 502)
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())
        self.assertTrue(self.stored.exists())

    def test_the_endpoint_answers_delete(self):
        self.client.force_login(self.manager)
        with ExitStack() as stack:
            self.services(stack)
            response = self.client.delete(f'/api/contracts/{self.contract.pk}/')
        self.assertEqual((response.status_code, response.json()['success']), (200, True))
