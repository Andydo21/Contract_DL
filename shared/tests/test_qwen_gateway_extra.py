import unittest
from unittest.mock import Mock, patch

import requests

from shared.qwen_gateway import HEADERS, base_url, chat, is_connected


def completion(content):
    response = Mock()
    response.json.return_value = {'choices': [{'message': {'content': content}}]}
    return response


@patch.dict('os.environ', {'VLLM_BASE_URL': 'https://gateway.test/v1/', 'QWEN_MODEL_ID': 'test-model'})
class QwenChatTests(unittest.TestCase):
    def test_base_url_drops_the_trailing_slash(self):
        self.assertEqual(base_url(), 'https://gateway.test/v1')

    @patch('shared.qwen_gateway.requests.post')
    def test_plain_chat_returns_stripped_text_and_sends_both_messages(self, post):
        post.return_value = completion('  hello \n')
        self.assertEqual(chat('be brief', 'hi', max_tokens=50), 'hello')
        self.assertEqual(post.call_args.args[0], 'https://gateway.test/v1/chat/completions')
        body = post.call_args.kwargs['json']
        self.assertEqual([m['role'] for m in body['messages']], ['system', 'user'])
        self.assertEqual((body['model'], body['max_tokens']), ('test-model', 50))
        self.assertNotIn('response_format', body)
        self.assertEqual(post.call_args.kwargs['headers'], HEADERS)

    @patch('shared.qwen_gateway.requests.post')
    def test_json_output_requests_json_mode_and_parses_fenced_json(self, post):
        post.return_value = completion('```json\n{"a": 1}\n```')
        self.assertEqual(chat('s', 't', json_output=True), {'a': 1})
        self.assertEqual(post.call_args.kwargs['json']['response_format'], {'type': 'json_object'})

    @patch('shared.qwen_gateway.requests.post')
    def test_json_schema_takes_precedence_over_json_mode(self, post):
        post.return_value = completion('{"a": 1}')
        schema = {'type': 'object'}
        chat('s', 't', json_output=True, json_schema=schema)
        fmt = post.call_args.kwargs['json']['response_format']
        self.assertEqual(fmt['type'], 'json_schema')
        self.assertEqual(fmt['json_schema']['schema'], schema)

    @patch('shared.qwen_gateway.requests.post')
    def test_json_array_is_rejected(self, post):
        post.return_value = completion('[1, 2]')
        with self.assertRaises(ValueError):
            chat('s', 't', json_output=True)

    @patch('shared.qwen_gateway.requests.post')
    def test_http_error_is_propagated(self, post):
        post.return_value.raise_for_status.side_effect = requests.HTTPError('502')
        with self.assertRaises(requests.HTTPError):
            chat('s', 't')

    def test_chat_without_a_configured_gateway_fails_fast(self):
        with patch.dict('os.environ', {'VLLM_BASE_URL': ''}), patch('shared.qwen_gateway.requests.post') as post:
            with self.assertRaises(RuntimeError):
                chat('s', 't')
        post.assert_not_called()


class QwenHealthTests(unittest.TestCase):
    @patch.dict('os.environ', {'VLLM_BASE_URL': ''})
    @patch('shared.qwen_gateway.requests.get')
    def test_legacy_health_endpoint_is_used_without_a_gateway(self, get):
        get.return_value = Mock(ok=True)
        get.return_value.json.return_value = {'status': 'healthy'}
        self.assertTrue(is_connected('http://legacy:8001/'))
        self.assertEqual(get.call_args.args[0], 'http://legacy:8001/health')

    @patch.dict('os.environ', {'VLLM_BASE_URL': ''})
    @patch('shared.qwen_gateway.requests.get')
    def test_legacy_unhealthy_status_is_not_connected(self, get):
        get.return_value = Mock(ok=True)
        get.return_value.json.return_value = {'status': 'loading'}
        self.assertFalse(is_connected('http://legacy:8001'))

    @patch.dict('os.environ', {'VLLM_BASE_URL': ''})
    @patch('shared.qwen_gateway.requests.get')
    def test_nothing_configured_is_not_connected_and_makes_no_call(self, get):
        self.assertFalse(is_connected())
        get.assert_not_called()

    @patch.dict('os.environ', {'VLLM_BASE_URL': 'https://gateway.test/v1'})
    @patch('shared.qwen_gateway.requests.get')
    def test_non_json_models_reply_is_not_connected(self, get):
        get.return_value = Mock(ok=True)
        get.return_value.json.side_effect = ValueError('html')
        self.assertFalse(is_connected())

    @patch.dict('os.environ', {'VLLM_BASE_URL': 'https://gateway.test/v1', 'QWEN_MODEL_ID': 'm'})
    @patch('shared.qwen_gateway.requests.get')
    def test_error_status_is_not_connected_even_if_model_listed(self, get):
        get.return_value = Mock(ok=False)
        get.return_value.json.return_value = {'data': [{'id': 'm'}]}
        self.assertFalse(is_connected())
