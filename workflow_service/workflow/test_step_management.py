"""Step management, dependencies, approval rules and tenant isolation, through the service layer and the real views."""
import json

from django.db import connections
from django.test import RequestFactory, TestCase
from django.urls import resolve

from . import views
from .models import Approval, StepDependency, Workflow, WorkflowStep
from .services import WorkflowService
from .tenant_guard import WorkflowTenantGuard


class WorkflowFixture:
    def make_workflow(self, names=('A', 'B', 'C'), version_id=1):
        workflow = Workflow.objects.create(version_id=version_id, workflow_name='WF', status='PENDING')
        steps = [WorkflowStep.objects.create(workflow=workflow, step_order=i, step_name=name, status='PENDING')
                 for i, name in enumerate(names, 1)]
        return workflow, steps

    def orders(self, workflow):
        return list(workflow.steps.order_by('step_order').values_list('step_name', 'step_order'))

    def post(self, view, body, *args):
        request = RequestFactory().post('/', json.dumps(body), content_type='application/json')
        return view(request, *args)


class StepManagementTests(WorkflowFixture, TestCase):
    def setUp(self):
        self.service = WorkflowService()
        self.workflow, (self.a, self.b, self.c) = self.make_workflow()

    def test_insert_in_the_middle_shifts_later_steps_down(self):
        new = self.service.insert_step(self.workflow.pk, 2, 'New', role_id=5)
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('New', 2), ('B', 3), ('C', 4)])
        self.assertEqual((new.status, new.role_id), ('PENDING', 5))

    def test_insert_at_the_front_shifts_every_step(self):
        self.service.insert_step(self.workflow.pk, 1, 'First')
        self.assertEqual(self.orders(self.workflow), [('First', 1), ('A', 2), ('B', 3), ('C', 4)])

    def test_insert_at_the_end_leaves_existing_steps(self):
        self.service.insert_step(self.workflow.pk, 4, 'Last')
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('B', 2), ('C', 3), ('Last', 4)])

    def test_insert_does_not_touch_other_workflows(self):
        other, (x,) = self.make_workflow(('X',), version_id=2)
        self.service.insert_step(self.workflow.pk, 1, 'First')
        self.assertEqual(self.orders(other), [('X', 1)])

    def test_insert_into_unknown_workflow_fails(self):
        with self.assertRaises(ValueError):
            self.service.insert_step(999999, 1, 'X')

    def test_insert_into_finished_workflow_fails(self):
        for status in ('COMPLETED', 'REJECTED'):
            Workflow.objects.filter(pk=self.workflow.pk).update(status=status)
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.service.insert_step(self.workflow.pk, 1, 'X')
        self.assertEqual(self.workflow.steps.count(), 3)

    def test_delete_renumbers_the_remaining_steps(self):
        self.service.delete_step(self.b.pk)
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('C', 2)])

    def test_delete_last_step_keeps_the_others_unchanged(self):
        self.service.delete_step(self.c.pk)
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('B', 2)])

    def test_delete_removes_dependencies_of_the_step(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.service.delete_step(self.b.pk)
        self.assertFalse(StepDependency.objects.exists())

    def test_delete_unknown_step_fails(self):
        with self.assertRaises(ValueError):
            self.service.delete_step(999999)

    def test_delete_from_finished_workflow_fails(self):
        Workflow.objects.filter(pk=self.workflow.pk).update(status='COMPLETED')
        with self.assertRaises(ValueError):
            self.service.delete_step(self.a.pk)
        self.assertEqual(self.workflow.steps.count(), 3)

    def test_signing_step_cannot_be_deleted_and_orders_stay(self):
        WorkflowStep.objects.filter(pk=self.b.pk).update(requires_signature=True)
        with self.assertRaises(ValueError):
            self.service.delete_step(self.b.pk)
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('B', 2), ('C', 3)])

    def test_update_role_changes_only_that_step(self):
        step = self.service.update_step_role(self.a.pk, 9)
        self.assertEqual(step.role_id, 9)
        self.b.refresh_from_db()
        self.assertIsNone(self.b.role_id)

    def test_update_role_of_unknown_step_fails(self):
        with self.assertRaises(WorkflowStep.DoesNotExist):
            self.service.update_step_role(999999, 1)

    def test_insert_view_returns_the_created_step(self):
        response = self.post(views.insert_step_view, {'step_order': 2, 'step_name': 'New', 'role_id': 6}, self.workflow.pk)
        self.assertEqual(response.status_code, 201)
        step = json.loads(response.content)['step']
        self.assertEqual((step['step_name'], step['step_order'], step['role_id']), ('New', 2, 6))

    def test_insert_view_validates_input_and_method(self):
        self.assertEqual(self.post(views.insert_step_view, {'step_name': 'x'}, self.workflow.pk).status_code, 400)
        self.assertEqual(self.post(views.insert_step_view, {'step_order': 1}, self.workflow.pk).status_code, 400)
        self.assertEqual(self.post(views.insert_step_view, {'step_order': 1, 'step_name': 'x'}, 999999).status_code, 400)
        get = RequestFactory().get('/')
        self.assertEqual(views.insert_step_view(get, self.workflow.pk).status_code, 405)

    def test_delete_view_reports_signing_step_as_bad_request(self):
        WorkflowStep.objects.filter(pk=self.a.pk).update(requires_signature=True)
        refused = self.post(views.delete_step_view, {}, self.a.pk)
        removed = self.post(views.delete_step_view, {}, self.b.pk)
        self.assertEqual((refused.status_code, removed.status_code), (400, 200))

    def test_update_role_view(self):
        ok = self.post(views.update_step_role, {'role_id': 7}, self.a.pk)
        missing = self.post(views.update_step_role, {}, self.a.pk)
        unknown = self.post(views.update_step_role, {'role_id': 7}, 999999)
        self.assertEqual((ok.status_code, missing.status_code, unknown.status_code), (200, 400, 400))
        self.assertEqual(json.loads(ok.content)['role_id'], 7)


class DependencyTests(WorkflowFixture, TestCase):
    def setUp(self):
        self.service = WorkflowService()
        self.workflow, (self.a, self.b, self.c) = self.make_workflow()

    def test_add_dependency_creates_the_link(self):
        dep = self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.assertEqual((dep.prerequisite_step_id, dep.dependent_step_id), (self.a.pk, self.b.pk))

    def test_adding_the_same_link_twice_keeps_one(self):
        first = self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        second = self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StepDependency.objects.count(), 1)

    def test_self_dependency_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, self.a.pk, self.a.pk)
        self.assertFalse(StepDependency.objects.exists())

    def test_direct_and_transitive_cycles_are_rejected(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.service.add_dependency(self.workflow.pk, self.b.pk, self.c.pk)
        for pre, dep in ((self.b, self.a), (self.c, self.a), (self.c, self.b)):
            with self.subTest(pre=pre.step_name, dep=dep.step_name), self.assertRaises(ValueError):
                self.service.add_dependency(self.workflow.pk, pre.pk, dep.pk)
        self.assertEqual(StepDependency.objects.count(), 2)

    def test_diamond_shape_is_not_a_cycle(self):
        d = WorkflowStep.objects.create(workflow=self.workflow, step_order=4, step_name='D', status='PENDING')
        for pre, dep in ((self.a, self.b), (self.a, self.c), (self.b, d), (self.c, d)):
            self.service.add_dependency(self.workflow.pk, pre.pk, dep.pk)
        self.assertEqual(StepDependency.objects.count(), 4)

    def test_steps_from_another_workflow_are_rejected(self):
        other, (x,) = self.make_workflow(('X',), version_id=2)
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, self.a.pk, x.pk)
        with self.assertRaises(ValueError):
            self.service.add_dependency(other.pk, self.a.pk, x.pk)

    def test_unknown_step_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.add_dependency(self.workflow.pk, self.a.pk, 999999)

    def test_delete_dependency_removes_only_that_link(self):
        keep = self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        drop = self.service.add_dependency(self.workflow.pk, self.b.pk, self.c.pk)
        self.service.delete_dependency(drop.pk)
        self.assertEqual(list(StepDependency.objects.values_list('pk', flat=True)), [keep.pk])

    def test_delete_unknown_dependency_fails(self):
        with self.assertRaises(ValueError):
            self.service.delete_dependency(999999)

    def test_dependency_views(self):
        body = {'prerequisite_step_id': self.a.pk, 'dependent_step_id': self.b.pk}
        created = self.post(views.add_dependency_view, body, self.workflow.pk)
        self.assertEqual(created.status_code, 201)
        dep = json.loads(created.content)['dependency']
        self.assertEqual((dep['prerequisite_step_name'], dep['dependent_step_name']), ('A', 'B'))
        cycle = self.post(views.add_dependency_view,
                          {'prerequisite_step_id': self.b.pk, 'dependent_step_id': self.a.pk}, self.workflow.pk)
        selfish = self.post(views.add_dependency_view,
                            {'prerequisite_step_id': self.a.pk, 'dependent_step_id': self.a.pk}, self.workflow.pk)
        incomplete = self.post(views.add_dependency_view, {'prerequisite_step_id': self.a.pk}, self.workflow.pk)
        self.assertEqual((cycle.status_code, selfish.status_code, incomplete.status_code), (400, 400, 400))
        deleted = self.post(views.delete_dependency_view, {}, dep['id'])
        again = self.post(views.delete_dependency_view, {}, dep['id'])
        self.assertEqual((deleted.status_code, again.status_code), (200, 400))

    def test_serialized_workflow_shows_blocking_links(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        detail = self.service.get_workflow_detail_dict(self.workflow.pk)
        self.assertTrue(detail['dependencies'][0]['is_blocking'])
        step_b = next(s for s in detail['steps'] if s['step_name'] == 'B')
        self.assertTrue(step_b['prerequisites'][0]['is_blocking'])
        self.service.approve_step(self.a.pk, 1, 'APPROVED')
        detail = self.service.get_workflow_detail_dict(self.workflow.pk)
        self.assertFalse(detail['dependencies'][0]['is_blocking'])


class ApproveTests(WorkflowFixture, TestCase):
    def setUp(self):
        self.service = WorkflowService()
        self.workflow, (self.a, self.b, self.c) = self.make_workflow()

    def test_dependent_step_waits_for_its_prerequisite(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        with self.assertRaises(ValueError) as caught:
            self.service.approve_step(self.b.pk, 1, 'APPROVED')
        self.assertIn("'A'", str(caught.exception))
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'PENDING')
        self.assertFalse(Approval.objects.exists())
        self.service.approve_step(self.a.pk, 1, 'APPROVED')
        self.service.approve_step(self.b.pk, 1, 'APPROVED')
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'APPROVED')

    def test_rejected_prerequisite_keeps_dependent_blocked(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.service.approve_step(self.a.pk, 1, 'REJECTED')
        with self.assertRaises(ValueError):
            self.service.approve_step(self.b.pk, 1, 'APPROVED')

    def test_force_complete_is_also_blocked_by_dependencies(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        with self.assertRaises(ValueError):
            self.service.approve_step(self.b.pk, 1, 'FORCE_COMPLETE', is_manager=True)

    def test_rejecting_a_blocked_step_is_still_allowed(self):
        self.service.add_dependency(self.workflow.pk, self.a.pk, self.b.pk)
        self.service.approve_step(self.b.pk, 1, 'REJECTED')
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'REJECTED')

    def test_rejection_rejects_the_whole_workflow(self):
        self.service.approve_step(self.a.pk, 1, 'REJECTED', comment='no')
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.status, 'REJECTED')
        self.assertIsNotNone(self.workflow.completed_at)

    def test_approving_some_steps_keeps_workflow_in_progress_then_completes(self):
        self.service.approve_step(self.a.pk, 1, 'APPROVED')
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.status, 'IN_PROGRESS')
        self.assertIsNone(self.workflow.completed_at)
        self.service.approve_step(self.b.pk, 1, 'APPROVED')
        self.service.approve_step(self.c.pk, 1, 'APPROVED')
        self.workflow.refresh_from_db()
        self.assertEqual(self.workflow.status, 'COMPLETED')
        self.assertIsNotNone(self.workflow.completed_at)

    def test_comment_and_user_are_stored_and_serialized(self):
        self.service.approve_step(self.a.pk, 42, 'APPROVED', comment='looks fine')
        approval = Approval.objects.get()
        self.assertEqual((approval.user_id, approval.status, approval.comment), (42, 'APPROVED', 'looks fine'))
        self.assertIsNotNone(approval.approved_at)
        step = next(s for s in self.service.get_workflow_detail_dict(self.workflow.pk)['steps'] if s['id'] == self.a.pk)
        self.assertEqual(step['comment'], 'looks fine')
        self.assertEqual(step['approvals'][0]['user_id'], 42)

    def test_manager_force_complete_uses_default_comment(self):
        self.service.approve_step(self.a.pk, 1, 'FORCE_COMPLETE', is_manager=True)
        approval = Approval.objects.get()
        self.assertEqual(approval.status, 'APPROVED')
        self.assertIn('Manager', approval.comment)

    def test_unknown_action_and_unknown_step_are_refused(self):
        with self.assertRaises(ValueError):
            self.service.approve_step(self.a.pk, 1, 'MAYBE')
        with self.assertRaises(ValueError):
            self.service.approve_step(999999, 1, 'APPROVED')
        self.assertFalse(Approval.objects.exists())

    def test_view_returns_step_and_workflow_status_with_comment(self):
        response = self.post(views.approve_step, {'action': 'APPROVED', 'user_id': 3, 'comment': 'ok'}, self.a.pk)
        body = json.loads(response.content)
        self.assertEqual((response.status_code, body['step_status'], body['workflow_status']), (200, 'APPROVED', 'IN_PROGRESS'))
        self.assertEqual(Approval.objects.get().comment, 'ok')

    def test_view_rejects_bad_json_and_get(self):
        bad = views.approve_step(RequestFactory().post('/', 'not json', content_type='application/json'), self.a.pk)
        get = views.approve_step(RequestFactory().get('/'), self.a.pk)
        self.assertEqual((bad.status_code, get.status_code), (400, 405))


class CrossTenantTests(WorkflowFixture, TestCase):
    """Company 1 owns contract version 1; users 5 and 6 belong to company 2; user 2 is company 1 staff."""
    databases = {'default', 'contract_db'}

    def setUp(self):
        with connections['contract_db'].cursor() as c:
            c.execute('CREATE TABLE contracts_role (id integer, role_name text)')
            c.execute('CREATE TABLE contracts_user (id integer,company_id integer,is_active integer,is_superuser integer,role_id integer)')
            c.execute('CREATE TABLE contracts_contract (id integer, company_id integer)')
            c.execute('CREATE TABLE contracts_contractversion (id integer, contract_id integer)')
            c.execute("INSERT INTO contracts_role VALUES (4,'SIGNER'),(5,'MANAGER')")
            c.execute('INSERT INTO contracts_user VALUES (1,1,1,0,5),(2,1,1,0,4),(5,2,1,0,5),(6,2,1,0,4),(9,NULL,1,1,5)')
            c.execute('INSERT INTO contracts_contract VALUES (1,1)')
            c.execute('INSERT INTO contracts_contractversion VALUES (1,1)')
        self.workflow, (self.a, self.b, self.c) = self.make_workflow()
        WorkflowStep.objects.filter(pk=self.a.pk).update(role_id=4)
        self.dep = WorkflowService().add_dependency(self.workflow.pk, self.b.pk, self.c.pk)

        def route(request):
            match = resolve(request.path)
            return match.func(request, **match.kwargs)
        self.guard = WorkflowTenantGuard(route)

    def call(self, user_id, method, path, body=None):
        factory = RequestFactory()
        if method == 'GET':
            request = factory.get(path)
        else:
            request = factory.post(path, json.dumps(body or {}), content_type='application/json')
        request.jwt_user_id = user_id
        return self.guard(request)

    def test_other_company_manager_cannot_read_the_workflow(self):
        for path in (f'/workflows/1/', f'/workflows/detail/{self.workflow.pk}/'):
            with self.subTest(path=path):
                self.assertEqual(self.call(5, 'GET', path).status_code, 404)

    def test_other_company_manager_cannot_change_steps_or_dependencies(self):
        attempts = [
            (f'/workflows/{self.workflow.pk}/insert_step/', {'step_order': 1, 'step_name': 'Evil'}),
            (f'/workflows/steps/{self.b.pk}/delete/', {}),
            (f'/workflows/steps/{self.b.pk}/update_role/', {'role_id': 9}),
            (f'/workflows/{self.workflow.pk}/dependencies/add/',
             {'prerequisite_step_id': self.a.pk, 'dependent_step_id': self.b.pk}),
            (f'/dependencies/{self.dep.pk}/delete/', {}),
        ]
        for path, body in attempts:
            with self.subTest(path=path):
                self.assertEqual(self.call(5, 'POST', path, body).status_code, 404)
        self.assertEqual(self.orders(self.workflow), [('A', 1), ('B', 2), ('C', 3)])
        self.assertEqual(StepDependency.objects.count(), 1)
        self.b.refresh_from_db()
        self.assertIsNone(self.b.role_id)

    def test_other_company_user_cannot_approve_even_with_matching_role(self):
        response = self.call(6, 'POST', f'/workflows/steps/{self.a.pk}/approve/', {'action': 'APPROVED'})
        self.assertEqual(response.status_code, 404)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, 'PENDING')
        self.assertFalse(Approval.objects.exists())

    def test_other_company_cannot_delete_the_contracts_workflows(self):
        response = self.call(5, 'POST', '/workflows/versions/1/delete/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Workflow.objects.filter(pk=self.workflow.pk).exists())

    def test_own_company_manager_can_insert_and_delete_steps(self):
        inserted = self.call(1, 'POST', f'/workflows/{self.workflow.pk}/insert_step/', {'step_order': 1, 'step_name': 'New'})
        self.assertEqual(inserted.status_code, 201)
        removed = self.call(1, 'POST', f'/workflows/steps/{self.c.pk}/delete/')
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.orders(self.workflow), [('New', 1), ('A', 2), ('B', 3)])

    def test_own_company_staff_cannot_administer_steps(self):
        response = self.call(2, 'POST', f'/workflows/steps/{self.b.pk}/delete/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.workflow.steps.count(), 3)

    def test_staff_with_the_wrong_role_cannot_approve_and_right_role_can(self):
        WorkflowStep.objects.filter(pk=self.b.pk).update(role_id=5)
        wrong = self.call(2, 'POST', f'/workflows/steps/{self.b.pk}/approve/', {'action': 'APPROVED'})
        right = self.call(2, 'POST', f'/workflows/steps/{self.a.pk}/approve/', {'action': 'APPROVED', 'comment': 'fine'})
        self.assertEqual((wrong.status_code, right.status_code), (403, 200))
        self.assertEqual(Approval.objects.get().comment, 'fine')

    def test_approver_identity_comes_from_the_token_not_the_body(self):
        self.call(2, 'POST', f'/workflows/steps/{self.a.pk}/approve/', {'action': 'APPROVED', 'user_id': 77})
        self.assertEqual(Approval.objects.get().user_id, 2)

    def test_superuser_can_reach_every_company(self):
        self.assertEqual(self.call(9, 'GET', '/workflows/1/').status_code, 200)

    def test_unknown_user_is_denied(self):
        self.assertEqual(self.call(12345, 'GET', '/workflows/1/').status_code, 403)

    def test_malformed_body_is_a_bad_request(self):
        request = RequestFactory().post(f'/workflows/{self.workflow.pk}/insert_step/', '[1]', content_type='application/json')
        request.jwt_user_id = 1
        self.assertEqual(self.guard(request).status_code, 400)

    def test_system_identity_with_token_may_read_but_not_administer(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {'WORKFLOW_SERVICE_TOKEN': 'sys'}):
            def system(method, path):
                request = RequestFactory().get(path, HTTP_X_WORKFLOW_SERVICE_TOKEN='sys') if method == 'GET' else \
                    RequestFactory().post(path, '{}', content_type='application/json', HTTP_X_WORKFLOW_SERVICE_TOKEN='sys')
                request.jwt_user_id = 0
                return self.guard(request)
            self.assertEqual(system('GET', '/workflows/1/').status_code, 200)
            self.assertEqual(system('POST', f'/workflows/steps/{self.b.pk}/delete/').status_code, 403)
            self.assertEqual(system('POST', f'/workflows/steps/{self.a.pk}/approve/').status_code, 403)
