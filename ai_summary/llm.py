"""OpenAI-compatible vLLM client for the summary model."""
import json
import os
import re
import requests

HEADERS = {'ngrok-skip-browser-warning': 'true'}
DEFAULT_MODEL = 'phamthanhfd/contract-summary-qwen3-1.7b'


class LLMError(RuntimeError):
    pass


def base_url():
    return (os.getenv('SUMMARY_LLM_URL') or os.getenv('VLLM_BASE_URL', '')).rstrip('/')


def model_id():
    return os.getenv('SUMMARY_MODEL_ID', DEFAULT_MODEL)


def is_connected():
    if not base_url():
        return False
    try:
        response = requests.get(base_url() + '/models', headers=HEADERS, timeout=5)
        return response.ok and any(item.get('id') == model_id() for item in response.json().get('data', []))
    except (requests.RequestException, ValueError, AttributeError):
        return False


def _parse(content):
    fenced = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError('expected a JSON object')
    return data


def chat_json(system, user, schema, max_tokens, model=None):
    """One schema-constrained call; a malformed reply is retried once before failing.

    The parsed object also carries '_content' (the raw JSON text) and '_tokens' ([(token, logprob)]),
    used to grade per-field confidence; callers strip both before use.
    """
    if not base_url():
        raise LLMError('SUMMARY_LLM_URL / VLLM_BASE_URL is not configured')
    body = dict(model=model or model_id(), temperature=0, max_tokens=max_tokens,
                messages=[dict(role='system', content=system), dict(role='user', content=user)],
                response_format=dict(type='json_schema', json_schema=dict(name='contract_summary', strict=True, schema=schema)),
                # Hybrid Qwen3 checkpoints would otherwise spend tokens on <think>; other templates ignore it.
                chat_template_kwargs=dict(enable_thinking=False),
                logprobs=os.getenv('SUMMARY_LOGPROBS', '1') == '1')
    timeout = float(os.getenv('SUMMARY_LLM_TIMEOUT', '180'))
    error = None
    for _ in range(2):
        try:
            response = requests.post(base_url() + '/chat/completions', json=body, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            choice = response.json()['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise LLMError('summary model hit max_tokens before finishing the JSON')
            content = choice['message']['content']
            data = _parse(content)
            tokens = ((choice.get('logprobs') or {}).get('content')) or []
            data['_content'] = content
            # Byte pieces, not token strings: one Vietnamese character can span several tokens.
            data['_tokens'] = [(bytes(t['bytes']) if t.get('bytes') is not None else t['token'].encode('utf-8'), t['logprob'])
                               for t in tokens if 'logprob' in t]
            return data
        except requests.RequestException as exc:
            raise LLMError(f'summary model request failed: {exc}') from exc
        except (LLMError, ValueError, KeyError, IndexError, TypeError) as exc:
            error = exc
    raise LLMError(f'summary model returned unusable output: {error}')
