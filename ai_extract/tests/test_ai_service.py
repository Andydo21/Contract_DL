"""The web container hands model calls and jobs to the AI service (riskdl_ai)."""
import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from ai_extract.services import ai_service_client, bulk_service
from ai_extract.services import contract_pipeline_service as qwen
from ai_extract.views import ai_internal_views

WEB = dict(AI_SERVICE_URL='http://ai:8000', AI_SERVICE_ROLE='web', AI_SERVICE_TOKEN='t0ken', AI_SERVICE_TIMEOUT=60)
AI = dict(AI_SERVICE_URL='', AI_SERVICE_ROLE='ai', AI_SERVICE_TOKEN='t0ken')


class DelegationTests(SimpleTestCase):
    @override_settings(**WEB)
    def test_the_web_container_sends_a_qwen_call_to_the_ai_service(self):
        answer = Mock(ok=True, status_code=200, json=lambda: dict(result=dict(summary='ok')))
        with patch.object(ai_service_client.requests, 'post', return_value=answer) as post:
            self.assertEqual(qwen.request_qwen('summarize', dict(clauses=[])), dict(summary='ok'))
        url = post.call_args.args[0]
        self.assertEqual((url, post.call_args.kwargs['headers']['X-AI-Token']), ('http://ai:8000/internal/ai/qwen/', 't0ken'))
        self.assertEqual(json.loads(post.call_args.kwargs['data']), dict(task='summarize', payload=dict(clauses=[])))

    @override_settings(**WEB)
    def test_an_error_in_the_ai_service_is_raised_again_with_its_own_class(self):
        error = dict(type='QwenContextLimitError', message='too long', args=[16384, 17000, 800])
        answer = Mock(ok=False, status_code=502, json=lambda: dict(error=error))
        with patch.object(ai_service_client.requests, 'post', return_value=answer):
            with self.assertRaises(qwen.QwenContextLimitError) as raised:
                qwen.request_qwen('contract_risk_review', {})
        self.assertEqual((raised.exception.capacity, raised.exception.prompt_tokens), (16384, 17000))

    @override_settings(**AI)
    def test_the_ai_service_itself_runs_the_call(self):
        self.assertFalse(ai_service_client.delegated())


class InternalEndpointTests(SimpleTestCase):
    def post(self, token='t0ken'):
        return RequestFactory().post('/internal/ai/qwen/', data=json.dumps(dict(task='summarize', payload={})),
                                     content_type='application/json', HTTP_X_AI_TOKEN=token)

    @override_settings(**WEB)
    def test_the_endpoints_do_not_exist_outside_the_ai_service(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            ai_internal_views.qwen(self.post())

    @override_settings(**AI)
    def test_a_wrong_token_is_refused_and_the_right_one_runs_the_model_call(self):
        self.assertEqual(ai_internal_views.qwen(self.post('wrong')).status_code, 403)
        with patch.object(qwen, 'request_qwen', return_value=dict(summary='ok')):
            response = ai_internal_views.qwen(self.post())
        self.assertEqual(json.loads(response.content), dict(result=dict(summary='ok')))


class JobQueueTests(SimpleTestCase):
    def jobs(self, *rows):
        return patch.object(bulk_service, 'jobs', return_value=list(rows))

    @override_settings(**WEB)
    def test_the_web_container_queues_jobs_and_leaves_them_to_the_ai_service(self):
        waiting = dict(id='a' * 32, status='waiting', items=[])
        with self.jobs(waiting), patch.object(bulk_service, 'launch') as launch:
            self.assertIsNone(bulk_service.active_job())
        launch.assert_not_called()

    @override_settings(**WEB)
    def test_a_job_running_in_another_container_is_not_judged_by_its_pid(self):
        running = dict(id='b' * 32, status='running', items=[], pid=12345, host='riskdl-ai-container')
        with self.jobs(running), patch.object(bulk_service, 'write_job') as write:
            self.assertEqual(bulk_service.active_job()['id'], 'b' * 32)
        write.assert_not_called()

    @override_settings(**AI)
    def test_the_ai_service_starts_the_oldest_waiting_job(self):
        waiting = dict(id='c' * 32, status='waiting', items=[])
        with self.jobs(waiting), patch.object(bulk_service, 'launch', return_value=waiting) as launch:
            bulk_service.active_job()
        launch.assert_called_once_with(waiting)
