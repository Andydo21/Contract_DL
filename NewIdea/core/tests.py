import json
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from .models import ExpertCase, CaseAuditEvent
from .case_library import similar_cases


class ContractModeTests(TestCase):
    def test_retired_writes_are_not_exposed(self):
        for endpoint in ('expert_answer', 'expert_consult', 'contribute_knowledge', 'clear_chat_history'):
            self.assertEqual(self.client.post(f'/api/{endpoint}/').status_code, 404)

    @override_settings(NEWIDEA_MODE='contracts',CONTRACT_WEB_URL='http://localhost:8000')
    def test_chat_opens_authenticated_main_web_search(self):
        response=self.client.get('/chat/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,'http://localhost:8000/newidea/')

    @override_settings(NEWIDEA_MODE='contracts')
    def test_old_anonymous_search_cannot_read_contract_indexes(self):
        response=self.client.post('/api/ask/',json.dumps({'query':'payment'}),content_type='application/json')
        self.assertEqual(response.status_code,404)


@override_settings(NEWIDEA_MODE='prototype', ROOT_URLCONF='core.prototype_test_urls')
class CaseLibraryTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(username='author', password='test-only')
        self.reviewer = get_user_model().objects.create_user(username='reviewer', is_staff=True)
        self.fields = dict(title='Overheat E-404', machine='M12 rev2', symptom='E-404 motor hot',
                           root_cause='Cooling fan stopped', solution='Replace fan under SOP',
                           verification='Measured temperature after repair',
                           applicability='Only M12 rev2; isolate supply first', source_reference='SOP-023 p4')

    def post(self, **data):
        return self.client.post('/api/cases/', json.dumps(data), content_type='application/json')

    def create_case(self):
        self.client.force_login(self.author)
        response = self.post(**self.fields)
        self.assertEqual(response.status_code, 200)
        return response.json()['case']['id']

    def approve(self, pk):
        self.client.force_login(self.reviewer)
        return self.post(action='approve', id=pk)

    def test_anonymous_cannot_write(self):
        self.assertEqual(self.post(**self.fields).status_code, 401)

    def test_staff_cannot_approve_own_case(self):
        self.client.force_login(self.reviewer)
        pk = self.post(**self.fields).json()['case']['id']
        self.assertEqual(self.post(action='approve', id=pk).status_code, 403)

    def test_drafts_not_retrieved(self):
        self.create_case()
        self.assertEqual(similar_cases('E-404', 'M12 rev2'), [])

    def test_only_staff_approves(self):
        pk = self.create_case()
        self.assertEqual(self.post(action='approve', id=pk).status_code, 403)

    def test_missing_verification_blocks_approval(self):
        self.fields['verification'] = ''
        pk = self.create_case()
        self.assertEqual(self.approve(pk).status_code, 400)
        self.assertEqual(ExpertCase.objects.get(pk=pk).status, 'draft')

    def test_machine_revision_filter_and_audit(self):
        pk = self.create_case()
        self.assertEqual(self.approve(pk).status_code, 200)
        self.assertEqual(len(similar_cases('E-404', 'M12 rev2')), 1)
        self.assertEqual(similar_cases('E-404', 'M12 rev1'), [])
        self.assertEqual(CaseAuditEvent.objects.filter(case_id=pk).count(), 2)

    def test_revision_preserves_published_case_until_approval(self):
        pk = self.create_case()
        self.approve(pk)
        self.client.force_login(self.author)
        response = self.post(action='revise', id=pk, solution='New verified repair')
        new_pk = response.json()['case']['id']
        self.assertEqual(response.json()['case']['revision'], 2)
        self.assertEqual(similar_cases('E-404')[0]['id'], pk)
        self.approve(new_pk)
        self.assertEqual(ExpertCase.objects.get(pk=pk).status, 'deprecated')
        self.assertEqual(similar_cases('E-404')[0]['id'], new_pk)
        self.assertTrue(CaseAuditEvent.objects.filter(case_id=pk, action='superseded').exists())

    def test_deprecated_cases_not_reused(self):
        pk = self.create_case()
        self.approve(pk)
        self.assertEqual(self.post(action='deprecate', id=pk).status_code, 200)
        self.assertEqual(similar_cases('E-404'), [])

    def test_invalid_payload_and_not_found(self):
        self.client.force_login(self.author)
        self.assertEqual(self.post(title=['invalid']).status_code, 400)
        self.assertEqual(self.post(action='revise', id=99999).status_code, 404)

    def test_other_author_cannot_revise(self):
        pk = self.create_case()
        stranger = get_user_model().objects.create_user(username='stranger')
        self.client.force_login(stranger)
        self.assertEqual(self.post(action='revise', id=pk).status_code, 403)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author)
        self.assertEqual(client.post('/api/cases/', json.dumps(self.fields),
                                     content_type='application/json').status_code, 403)

    def test_page_renders(self):
        response = self.client.get('/cases/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'case-form')

    def test_old_draft_cannot_replace_new_revision(self):
        pk = self.create_case()
        self.post(action='revise', id=pk)
        self.assertEqual(self.approve(pk).status_code, 400)
