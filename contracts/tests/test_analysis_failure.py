"""A failed AI call must leave the previous risk analysis in place."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from ai_extract.models import Clause
from ai_extract.services.contract_pipeline_service import QwenGatewayError
from contracts.models import AIAnalysis, Company, Contract, ContractVersion
from contracts.services import ContractService


class AnalysisFailureTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='Tenant')
        self.contract = Contract.objects.create(title='Sale', contract_code='C-1', company=company)
        self.version = ContractVersion.objects.create(contract=self.contract, version_number=1)
        Clause.objects.create(version=self.version, clause_title='Điều 1', clause_content='Nội dung')
        self.previous = AIAnalysis.objects.create(version=self.version, model_name='old', overall_score=Decimal('5.0'), summary='Kết quả cũ')
        # The service reopens its connection after the slow AI call; keep this test's transaction open.
        closing = patch('django.db.connection.close')
        closing.start()
        self.addCleanup(closing.stop)

    def test_failed_ai_call_keeps_the_previous_analysis(self):
        with patch('NewIdea.services.clause_risk_service.review_version', side_effect=QwenGatewayError('down')), self.assertRaises(RuntimeError):
            ContractService().analyze_contract(self.contract.pk, user=object())
        self.assertEqual(list(AIAnalysis.objects.filter(version=self.version)), [self.previous])
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, 'DRAFT')

    def test_successful_ai_call_replaces_the_previous_analysis(self):
        reply = dict(overall_score=7, summary='Kết quả mới', findings=[])
        with patch('NewIdea.services.clause_risk_service.review_version', return_value=reply):
            ContractService().analyze_contract(self.contract.pk, user=object())
        self.assertEqual([a.summary for a in AIAnalysis.objects.filter(version=self.version)], ['Kết quả mới'])
