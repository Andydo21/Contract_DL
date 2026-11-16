"""The user marks a document as a legal text and sets its number, status and effective date; the law search then uses
it according to that status."""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai.ai_extract.models import LegalDocument
from contract.contracts.models import Company, Contract, Role
from contract.contracts.services import legal_mark_service
from ai.legal_ai.repositories.contract_repository import legal_contracts

EXTRACT = 'ai.ai_extract.services.bulk_service.extract_after_upload'


class LegalMarkTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='Tenant')
        self.contract = Contract.objects.create(title='Luật Trọng tài thương mại', contract_code='LTTTM', company=company)
        manager = Role.objects.create(role_name='MANAGER')
        self.manager = get_user_model().objects.create_user(username='m', password='x', company=company, role=manager)
        self.staff = get_user_model().objects.create_user(username='s', password='x', company=company)
        self.stranger = get_user_model().objects.create_user(username='o', password='x', role=manager,
                                                             company=Company.objects.create(company_name='Other'))

    def mark(self, user=None, **data):
        return legal_mark_service.contract_legal(self.contract.pk, user or self.manager, 'POST', dict(dict(is_legal=True), **data))

    def test_marking_records_the_details_and_extracts_the_document_again(self):
        with patch(EXTRACT, return_value=dict(id='job1')) as extract:
            result = self.mark(number=' 54/2010/QH12 ', status=LegalDocument.FULLY_IN_FORCE, effective_on='2011-01-01')
        self.assertEqual(result.status, 200)
        document = LegalDocument.objects.get(contract=self.contract)
        self.assertEqual((document.number, document.status, document.effective_on, document.title),
                         ('54/2010/QH12', 'Còn hiệu lực', date(2011, 1, 1), 'Luật Trọng tài thương mại'))
        self.assertEqual(result.payload['extraction_job_id'], 'job1')
        extract.assert_called_once()
        # Changing the details of a marked document does not extract it again.
        with patch(EXTRACT) as extract:
            self.mark(number='54/2010/QH12', status=LegalDocument.PARTLY_REPEALED)
        extract.assert_not_called()
        self.assertEqual(LegalDocument.objects.get(contract=self.contract).status, 'Hết hiệu lực một phần')

    def test_a_repealed_text_is_kept_but_never_searched_as_law(self):
        with patch(EXTRACT):
            self.mark(status=LegalDocument.FULLY_IN_FORCE)
            self.assertIn(self.contract, legal_contracts(self.manager))
            self.mark(status=LegalDocument.REPEALED)
        self.assertTrue(LegalDocument.objects.filter(contract=self.contract).exists())
        self.assertNotIn(self.contract, legal_contracts(self.manager))

    def test_a_text_not_yet_in_force_needs_its_date_and_counts_from_it(self):
        with patch(EXTRACT):
            self.assertEqual(self.mark(status=LegalDocument.NOT_YET_IN_FORCE).status, 400)
            self.mark(status=LegalDocument.NOT_YET_IN_FORCE, effective_on=(date.today() + timedelta(days=30)).isoformat())
            self.assertNotIn(self.contract, legal_contracts(self.manager))
            self.mark(status=LegalDocument.NOT_YET_IN_FORCE, effective_on=(date.today() - timedelta(days=1)).isoformat())
            self.assertIn(self.contract, legal_contracts(self.manager))

    def test_unmarking_removes_the_mark(self):
        with patch(EXTRACT, return_value=dict(id='job2')):
            self.mark()
            result = legal_mark_service.contract_legal(self.contract.pk, self.manager, 'POST', dict(is_legal=False))
        self.assertIsNone(result.payload['legal'])
        self.assertFalse(LegalDocument.objects.filter(contract=self.contract).exists())

    def test_only_a_manager_of_the_company_marks_and_values_are_checked(self):
        self.assertEqual(self.mark(user=self.staff).status, 403)
        self.assertEqual(self.mark(user=self.stranger).status, 403)
        with patch(EXTRACT):
            self.assertEqual(self.mark(status='Tự đặt').status, 400)
            self.assertEqual(self.mark(effective_on='01/01/2011').status, 400)
        self.assertFalse(LegalDocument.objects.exists())
        # Anyone of the company reads the mark.
        self.assertEqual(legal_mark_service.contract_legal(self.contract.pk, self.staff, 'GET', {}).status, 200)
