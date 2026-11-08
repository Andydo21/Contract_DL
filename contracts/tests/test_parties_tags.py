"""Parties the user enters and tags from the administrator's list."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from contracts.models import Company, Contract, ContractParty, Tag
from contracts.services import party_tag_service


class PartyTagTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Tenant')
        self.contract = Contract.objects.create(title='Mua bán', contract_code='C-PT', company=self.company)
        self.user = get_user_model().objects.create_user(username='u1', password='x', company=self.company)
        self.stranger = get_user_model().objects.create_user(username='u2', password='x',
                                                             company=Company.objects.create(company_name='Other'))

    def test_parties_are_replaced_in_the_order_entered_and_empty_rows_dropped(self):
        rows = [dict(party_type='Bên A', party_name=' Công ty  An Phát ', tax_code='0101'), dict(party_type='Bên B', party_name='')]
        result = party_tag_service.contract_parties(self.contract.pk, self.user, 'POST', dict(parties=rows))
        self.assertEqual(result.status, 200)
        self.assertEqual([(p.party_type, p.party_name, p.tax_code) for p in ContractParty.objects.all()], [('Bên A', 'Công ty An Phát', '0101')])
        bad = party_tag_service.contract_parties(self.contract.pk, self.user, 'POST', dict(parties=[dict(party_type='Bên C', party_name='X')]))
        self.assertEqual(bad.status, 400)

    def test_another_company_cannot_read_or_change_parties_or_tags(self):
        self.assertEqual(party_tag_service.contract_parties(self.contract.pk, self.stranger, 'GET', {}).status, 403)
        self.assertEqual(party_tag_service.contract_tags(self.contract.pk, self.stranger, 'POST', dict(tag_ids=[])).status, 403)

    def test_only_existing_tags_can_be_attached(self):
        tag = Tag.objects.create(tag_name='Mua bán hàng hóa')
        result = party_tag_service.contract_tags(self.contract.pk, self.user, 'POST', dict(tag_ids=[tag.pk, 999999]))
        self.assertEqual([t['name'] for t in result.payload['tags'] if t['selected']], ['Mua bán hàng hóa'])
        self.assertEqual(list(self.contract.tags.values_list('tag_name', flat=True)), ['Mua bán hàng hóa'])
