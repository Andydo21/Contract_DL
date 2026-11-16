"""A deleted contract leaves no vectors: every collection is filtered by app, company and contract."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai.ai_extract.services import contract_pipeline_service as pipeline


class DeleteContractPointsTests(SimpleTestCase):
    def test_points_of_the_contract_are_deleted_from_every_existing_collection(self):
        client = MagicMock()
        client.get_collections.return_value = SimpleNamespace(collections=[
            SimpleNamespace(name=pipeline.DENSE_COLLECTION), SimpleNamespace(name=pipeline.ENTITY_COLLECTION)])
        with patch.object(pipeline.PlanAQdrantClient, 'get', return_value=client):
            result = pipeline.PlanACollectionIndexer().delete_contract_points(company_id=1, contract_id=7)
        self.assertEqual(result[pipeline.COLPALI_COLLECTION], 'not_created')
        self.assertEqual(client.delete.call_count, 2)
        conditions = client.delete.call_args.kwargs['points_selector'].must
        self.assertEqual({(c.key, c.match.value) for c in conditions},
                         {('source_app', 'contract_dl'), ('company_id', 1), ('contract_id', 7)})
