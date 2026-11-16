"""Turning a legal text off and on from the admin page: off, it stays in store but search and risk analysis no longer
read it; on, they read it again."""
from django.contrib.admin.models import LogEntry
from django.test import TestCase, override_settings

from ai.ai_extract.models import LegalDocument
from ai.legal_ai.repositories import contract_repository, knowledge_repository
from contract.contracts.models import Company, Contract, User

URL = '/admin/ai_extract/legaldocument/'


@override_settings(DEMO_AUTO_LOGIN=False)
class LegalToggleTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Hệ thống', tax_code='000')
        self.admin = User.objects.create_superuser('root', 'r@x.test', 'pw', company=self.company)
        self.client.force_login(self.admin)

    def law(self, code, status=LegalDocument.FULLY_IN_FORCE):
        contract = Contract.objects.create(company=self.company, contract_code=code, title=f'Luật {code}')
        return knowledge_repository.mark_legal(contract, public=True, source_id=code, number=code, doc_type='Luật',
                                               status=status)

    def act(self, action, *documents):
        return self.client.post(URL, {'action': action, '_selected_action': [d.pk for d in documents]}, follow=True)

    def readable(self):
        return set(contract_repository.legal_contracts(self.admin).values_list('contract_code', flat=True))

    def test_turning_a_law_off_removes_it_from_search_but_keeps_it(self):
        old, new = self.law('91/2015/QH13'), self.law('85/2025/QH15')
        response = self.act('turn_off', old)
        self.assertEqual(response.status_code, 200)
        old.refresh_from_db()
        self.assertEqual(old.status, LegalDocument.REPEALED)
        self.assertTrue(LegalDocument.objects.filter(pk=old.pk).exists())  # kept in store
        self.assertEqual(self.readable(), {'85/2025/QH15'})
        self.assertTrue(LogEntry.objects.filter(object_id=str(old.pk)).exists())

    def test_turning_it_on_again_brings_it_back(self):
        old = self.law('91/2015/QH13', status=LegalDocument.REPEALED)
        self.assertEqual(self.readable(), set())
        self.act('turn_on', old)
        old.refresh_from_db()
        self.assertEqual(old.status, LegalDocument.FULLY_IN_FORCE)
        self.assertEqual(self.readable(), {'91/2015/QH13'})

    def test_on_restores_the_status_the_text_had(self):
        partly = self.law('123/2015', status=LegalDocument.PARTLY_REPEALED)
        future = self.law('03/2026', status=LegalDocument.NOT_YET_IN_FORCE)
        self.act('turn_off', partly, future)
        self.act('turn_on', partly, future)
        partly.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual((partly.status, future.status), (LegalDocument.PARTLY_REPEALED, LegalDocument.NOT_YET_IN_FORCE))
        self.assertEqual(partly.status_before_off, '')

    def test_on_leaves_a_text_that_was_not_turned_off(self):
        partly = self.law('123/2015', status=LegalDocument.PARTLY_REPEALED)
        self.act('turn_on', partly)
        partly.refresh_from_db()
        self.assertEqual(partly.status, LegalDocument.PARTLY_REPEALED)

    def test_several_laws_at_once_and_the_applied_column(self):
        a, b = self.law('A/1'), self.law('B/2', status=LegalDocument.PARTLY_REPEALED)
        self.act('turn_off', a, b)
        self.assertEqual(set(LegalDocument.objects.values_list('status', flat=True)), {LegalDocument.REPEALED})
        page = self.client.get(URL)
        self.assertContains(page, 'Dùng làm căn cứ')

    def test_only_staff_reach_the_admin_actions(self):
        staff = User.objects.create_user('staff', 's@x.test', 'pw', company=self.company)
        self.client.force_login(staff)
        law = self.law('C/3')
        self.act('turn_off', law)
        law.refresh_from_db()
        self.assertEqual(law.status, LegalDocument.FULLY_IN_FORCE)
