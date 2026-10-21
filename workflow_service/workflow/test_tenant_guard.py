import json
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.db import connections
from django.http import JsonResponse
from .models import Workflow, WorkflowStep
from .tenant_guard import WorkflowTenantGuard
from .repositories import WorkflowRepository


class WorkflowTenantTests(TestCase):
    databases = {'default', 'contract_db'}

    def setUp(self):
        with connections['contract_db'].cursor() as c:
            c.execute('CREATE TABLE contracts_role (id integer, role_name text)')
            c.execute('CREATE TABLE contracts_user (id integer,company_id integer,is_active integer,is_superuser integer,role_id integer)')
            c.execute('CREATE TABLE contracts_contract (id integer, company_id integer)')
            c.execute('CREATE TABLE contracts_contractversion (id integer, contract_id integer)')
            c.execute("INSERT INTO contracts_role VALUES (4,'SIGNER')")
            c.execute('INSERT INTO contracts_user VALUES (1,1,1,0,4),(2,2,1,0,4),(3,1,0,0,4)')
            c.execute('INSERT INTO contracts_contract VALUES (1,1)')
            c.execute('INSERT INTO contracts_contractversion VALUES (1,1)')
        w = Workflow.objects.create(version_id=1, workflow_name='Demo', status='IN_PROGRESS')
        self.step = WorkflowStep.objects.create(workflow=w, step_name='Review', step_order=1, role_id=4, status='PENDING')
        self.factory = RequestFactory()
        self.guard = WorkflowTenantGuard(lambda r: JsonResponse(json.loads(r.body or '{}')))

    def test_anonymous_request_is_denied(self):
        self.assertEqual(self.guard(self.factory.get('/workflows/all/')).status_code, 401)

    def test_foreign_company_version_is_denied(self):
        r = self.factory.get('/workflows/1/')
        r.jwt_user_id = 2
        self.assertEqual(self.guard(r).status_code, 404)

    def test_body_cannot_choose_user_company_or_manager_privilege(self):
        r = self.factory.post(f'/workflows/steps/{self.step.pk}/approve/', json.dumps({'user_id':2,'company_id':2,'is_manager':True}), content_type='application/json')
        r.jwt_user_id = 1
        response = self.guard(r)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {'user_id':1,'company_id':1,'is_manager':False})

    def test_inactive_user_is_denied(self):
        r = self.factory.get('/workflows/all/')
        r.jwt_user_id = 3
        self.assertEqual(self.guard(r).status_code, 403)

    def test_system_jwt_without_service_token_is_denied(self):
        r = self.factory.get('/workflows/1/')
        r.jwt_user_id = 0
        self.assertEqual(self.guard(r).status_code, 401)

    def test_database_failure_does_not_return_other_companies_workflows(self):
        with patch('django.db.connections') as db:
            db.__getitem__.return_value.cursor.side_effect = RuntimeError('offline')
            self.assertFalse(WorkflowRepository.get_workflows_by_company(1).exists())
