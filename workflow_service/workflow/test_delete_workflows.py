"""When the contract web deletes a contract it removes the version's workflows here, with steps and signatures;
only the system token (or a manager of the company) may do it."""
import json
import os
from unittest.mock import patch

from django.db import connections
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from .models import DigitalSignature, Workflow, WorkflowStep
from .services import WorkflowService
from .tenant_guard import WorkflowTenantGuard


class DeleteWorkflowsTests(TestCase):
    databases = {'default', 'contract_db'}

    def setUp(self):
        with connections['contract_db'].cursor() as c:
            c.execute('CREATE TABLE contracts_role (id integer, role_name text)')
            c.execute('CREATE TABLE contracts_user (id integer,company_id integer,is_active integer,is_superuser integer,role_id integer)')
            c.execute('CREATE TABLE contracts_contract (id integer, company_id integer)')
            c.execute('CREATE TABLE contracts_contractversion (id integer, contract_id integer)')
            c.execute("INSERT INTO contracts_role VALUES (4,'SIGNER')")
            c.execute('INSERT INTO contracts_user VALUES (1,1,1,0,4)')
            c.execute('INSERT INTO contracts_contract VALUES (1,1)')
            c.execute('INSERT INTO contracts_contractversion VALUES (7,1)')
        workflow = Workflow.objects.create(version_id=7, workflow_name='Duyệt', status='IN_PROGRESS')
        step = WorkflowStep.objects.create(workflow=workflow, step_name='Ký', step_order=1, role_id=4, status='COMPLETED')
        DigitalSignature.objects.create(step_id=step.pk, user_id=1, signature_hash='s')
        Workflow.objects.create(version_id=8, workflow_name='Khác', status='PENDING')
        self.guard = WorkflowTenantGuard(lambda r: JsonResponse({'passed': True}))

    def test_the_versions_workflows_go_with_their_steps_and_signatures(self):
        self.assertEqual(WorkflowService().delete_workflows_for_version(7), 1)
        self.assertFalse(Workflow.objects.filter(version_id=7).exists())
        self.assertFalse(WorkflowStep.objects.exists())
        self.assertFalse(DigitalSignature.objects.exists())
        self.assertTrue(Workflow.objects.filter(version_id=8).exists())

    @patch.dict(os.environ, {'WORKFLOW_SERVICE_TOKEN': 'svc'})
    def test_the_system_token_may_delete(self):
        request = RequestFactory().post('/workflows/versions/7/delete/', '{}', content_type='application/json',
                                        HTTP_X_WORKFLOW_SERVICE_TOKEN='svc')
        request.jwt_user_id = 0
        self.assertEqual(json.loads(self.guard(request).content), {'passed': True})

    def test_a_non_manager_may_not_delete(self):
        request = RequestFactory().post('/workflows/versions/7/delete/', '{}', content_type='application/json')
        request.jwt_user_id = 1
        self.assertEqual(self.guard(request).status_code, 403)
