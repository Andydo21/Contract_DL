"""The legal-text on/off switch of the "Quản trị hệ thống" page: who may see and switch which text, and that a text
turned off is no longer read as law while one turned on again gets its earlier status back."""
import json

from django.urls import reverse

from ai.ai_extract.models import LegalDocument
from ai.legal_ai.repositories import contract_repository, knowledge_repository
from contract.administration.tests.test_administration import AdminBase
from contract.contracts.models import AuditLog, Company, Contract


class LegalSwitchTests(AdminBase):
    def setUp(self):
        super().setUp()
        self.system = Company.objects.create(company_name='Hệ thống', tax_code='000')
        self.public = self.law(self.system, '91/2015/QH13', public=True)
        self.partly = self.law(self.system, '123/2015/NĐ-CP', public=True, status=LegalDocument.PARTLY_REPEALED)
        self.own = self.law(self.company, 'QC-01')
        self.foreign = self.law(self.other_company, 'QC-B')

    def law(self, company, code, public=False, status=LegalDocument.FULLY_IN_FORCE):
        contract = Contract.objects.create(company=company, contract_code=code, title=f'Văn bản {code}')
        return knowledge_repository.mark_legal(contract, public=public, source_id=code, number=code, doc_type='Luật', status=status)

    def switch(self, document, on):
        return self.client.post(reverse('api_admin_switch_legal', args=[document.pk]), json.dumps({'on': on}),
                                content_type='application/json')

    def numbers(self):
        return {row['number']: row for row in self.client.get(reverse('api_admin_legal_documents')).json()['documents']}

    def readable(self, user):
        return set(contract_repository.legal_contracts(user).values_list('contract_code', flat=True))

    def test_only_managers_reach_the_switch(self):
        self.assertEqual(self.client.get(reverse('api_admin_legal_documents')).status_code, 401)
        self.assertEqual(self.switch(self.public, False).status_code, 401)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('api_admin_legal_documents')).status_code, 403)
        self.assertEqual(self.switch(self.own, False).status_code, 403)

    def test_system_administrator_turns_public_law_off_and_on(self):
        self.client.force_login(self.superuser)
        self.assertEqual(len(self.numbers()), 4)
        response = self.switch(self.partly, False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['changed'], response.json()['document']['applied']), (True, False))
        self.assertNotIn('123/2015/NĐ-CP', self.readable(self.manager))
        self.assertTrue(LegalDocument.objects.filter(pk=self.partly.pk).exists())  # kept in store
        self.assertTrue(AuditLog.objects.filter(user=self.superuser, action__contains='123/2015/NĐ-CP').exists())
        response = self.switch(self.partly, True)
        self.assertEqual(response.json()['document']['status'], LegalDocument.PARTLY_REPEALED)  # the status it had
        self.assertIn('123/2015/NĐ-CP', self.readable(self.manager))

    def test_repeating_a_switch_changes_nothing(self):
        self.client.force_login(self.superuser)
        self.switch(self.public, False)
        switched = AuditLog.objects.filter(action__startswith='Legal text')
        self.assertEqual(switched.count(), 1)
        self.assertFalse(self.switch(self.public, False).json()['changed'])
        self.assertEqual(switched.count(), 1)
        self.assertFalse(self.switch(self.partly, True).json()['changed'])  # was never off
        self.partly.refresh_from_db()
        self.assertEqual(self.partly.status, LegalDocument.PARTLY_REPEALED)

    def test_manager_sees_public_law_read_only_and_switches_only_own_texts(self):
        self.client.force_login(self.manager)
        rows = self.numbers()
        self.assertEqual(set(rows), {'91/2015/QH13', '123/2015/NĐ-CP', 'QC-01'})  # not the other company's
        self.assertEqual((rows['91/2015/QH13']['can_switch'], rows['QC-01']['can_switch']), (False, True))
        self.assertEqual(self.switch(self.public, False).status_code, 403)
        self.assertEqual(self.switch(self.foreign, False).status_code, 404)
        self.assertEqual(self.switch(self.own, False).status_code, 200)
        self.public.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertEqual({self.public.status, self.foreign.status}, {LegalDocument.FULLY_IN_FORCE})
        self.assertNotIn('QC-01', self.readable(self.manager))

    def test_bad_requests(self):
        self.client.force_login(self.superuser)
        url = reverse('api_admin_switch_legal', args=[self.public.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, '{}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(reverse('api_admin_switch_legal', args=[999999]), json.dumps({'on': False}),
                                          content_type='application/json').status_code, 404)
