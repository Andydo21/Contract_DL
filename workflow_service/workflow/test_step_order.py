"""The execution order of a workflow: a step linked behind an unfinished step cannot be approved (400, not 404),
links cannot form a cycle, and removing the link frees the step."""
import json

from django.test import RequestFactory, TestCase

from . import views
from .models import StepDependency, Workflow, WorkflowStep
from .services import WorkflowService


class StepOrderTests(TestCase):
    def setUp(self):
        self.workflow = Workflow.objects.create(version_id=7, workflow_name='Duyệt', status='PENDING')
        self.first = WorkflowStep.objects.create(workflow=self.workflow, step_name='Rà soát', step_order=1)
        self.second = WorkflowStep.objects.create(workflow=self.workflow, step_name='Phê duyệt', step_order=2)
        self.service = WorkflowService()

    def approve(self, step):
        request = RequestFactory().post('/', json.dumps({'action': 'APPROVED', 'user_id': 1}), content_type='application/json')
        return views.approve_step(request, step.pk)

    def test_a_blocked_step_is_a_bad_request_and_unlinking_frees_it(self):
        dep = self.service.add_dependency(self.workflow.pk, self.first.pk, self.second.pk)
        response = self.approve(self.second)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Rà soát', json.loads(response.content)['error'])
        self.service.delete_dependency(dep.pk)
        self.assertFalse(StepDependency.objects.exists())
        self.assertEqual(self.approve(self.second).status_code, 200)

    def test_links_cannot_form_a_cycle_or_point_at_themselves(self):
        self.service.add_dependency(self.workflow.pk, self.first.pk, self.second.pk)
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, self.second.pk, self.first.pk)
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, self.first.pk, self.first.pk)

    def test_a_longer_cycle_is_refused_too(self):
        third = WorkflowStep.objects.create(workflow=self.workflow, step_name='Ký', step_order=3)
        self.service.add_dependency(self.workflow.pk, self.first.pk, self.second.pk)
        self.service.add_dependency(self.workflow.pk, self.second.pk, third.pk)
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, third.pk, self.first.pk)
        self.assertEqual(StepDependency.objects.count(), 2)

    def test_an_unknown_user_or_company_lists_no_workflow(self):
        from types import SimpleNamespace
        self.assertEqual(self.service.list_workflows_for_user(None), [])
        nobody = SimpleNamespace(is_authenticated=True, is_superuser=False, company_id=None)
        self.assertEqual(self.service.list_workflows_for_user(nobody), [])

    def test_a_missing_step_is_not_found(self):
        request = RequestFactory().post('/', json.dumps({'action': 'APPROVED'}), content_type='application/json')
        self.assertEqual(views.approve_step(request, 999999).status_code, 404)
