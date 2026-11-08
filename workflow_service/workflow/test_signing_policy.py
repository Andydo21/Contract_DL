from django.test import TestCase
from .models import Workflow, WorkflowStep
from .services import WorkflowService
from .repositories import WorkflowRepository


class SigningPolicyTests(TestCase):
    def setUp(self):
        self.workflow = Workflow.objects.create(version_id=1, workflow_name='Demo', status='IN_PROGRESS')
        self.service = WorkflowService()

    def test_new_signing_step_is_marked_explicitly(self):
        step = WorkflowRepository.create_step(self.workflow, 1, 'Contract Signing')
        self.assertTrue(step.requires_signature)

    def test_renaming_signing_step_cannot_bypass_signature(self):
        step = WorkflowStep.objects.create(workflow=self.workflow, step_order=1, step_name='Ordinary review', status='PENDING', requires_signature=True)
        for action in ['APPROVED', 'FORCE_COMPLETE']:
            with self.assertRaises(ValueError): self.service.approve_step(step.pk, 1, action, is_manager=True)
        step.refresh_from_db()
        self.assertEqual(step.status, 'PENDING')

    def test_signing_step_cannot_be_deleted(self):
        step = WorkflowStep.objects.create(workflow=self.workflow, step_order=1, step_name='Sign', status='PENDING', requires_signature=True)
        with self.assertRaises(ValueError): self.service.delete_step(step.pk)
        self.assertTrue(WorkflowStep.objects.filter(pk=step.pk).exists())

    def test_review_approval_does_not_create_fake_signature(self):
        from .models import DigitalSignature
        step = WorkflowStep.objects.create(workflow=self.workflow, step_order=1, step_name='Legal Review', status='PENDING')
        self.service.approve_step(step.pk, 1, 'APPROVED')
        step.refresh_from_db()
        self.assertEqual(step.status, 'APPROVED')
        self.assertFalse(DigitalSignature.objects.exists())

    def test_force_complete_requires_manager(self):
        step = WorkflowStep.objects.create(workflow=self.workflow, step_order=1, step_name='Review', status='PENDING')
        with self.assertRaises(ValueError): self.service.approve_step(step.pk, 1, 'FORCE_COMPLETE', is_manager=False)
