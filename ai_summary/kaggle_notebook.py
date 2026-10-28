# Kaggle notebook (GPU T4 x2): serve the summary model through vLLM's OpenAI-compatible API.
# Add a Kaggle secret named NGROK_AUTH_TOKEN (Add-ons -> Secrets); never paste the token here.
# Optional secret HF_TOKEN: needed only for private (fine-tuned) Hugging Face repos.
#
# Cell 1 — install. Verified on Kaggle: Python 3.13, vllm 0.32.0, torch 2.13.0+cu130, Tesla T4.
# Every new Kaggle session starts clean, so vLLM + torch + CUDA libraries (several GB) are installed again.
# uv downloads in parallel and installs much faster than pip; a re-run in the same session is skipped.
# Optional, faster still: once, run `!pip download "vllm==0.32.0" pyngrok -d /kaggle/working/wheels`,
# save the notebook version and add its output as a Dataset; later sessions then set WHEELS to its path
# and install from local files without downloading.
# import importlib.metadata, glob, subprocess
# WHEELS = next(iter(glob.glob('/kaggle/input/*/wheels')), None)
# try:
#     installed = importlib.metadata.version('vllm') == '0.32.0'
# except importlib.metadata.PackageNotFoundError:
#     installed = False
# if not installed:
#     subprocess.run('pip install -q uv', shell=True, check=True)
#     source = f'--offline --find-links {WHEELS}' if WHEELS else ''
#     subprocess.run(f'uv pip install --system --break-system-packages {source} "vllm==0.32.0" pyngrok', shell=True, check=True)
#     # Kaggle's torchaudio is built for CUDA 12.8; transformers imports it if present and vLLM then fails
#     # against torch cu130. The text model needs no audio, so remove it.
#     subprocess.run('pip uninstall -y -q torchaudio', shell=True)
# print('vllm', importlib.metadata.version('vllm'))

# Cell 2 — start the main model (GPU 0) and, optionally, a candidate (GPU 1) IN PARALLEL, behind one URL.
# Startup is a one-off per session: weight download, then vLLM compile + CUDA graph capture (1-3 min per
# model on T4). Both models load at the same time, so the wait is the slower one, not the sum.
# Set CANDIDATE_ID = None to serve only the main model.
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import requests
import uvicorn
from fastapi import FastAPI, Request, Response
from kaggle_secrets import UserSecretsClient
from pyngrok import conf, ngrok
from pyngrok.exception import PyngrokNgrokHTTPError

MODEL_ID = 'phamthanhfd/contract-summary-qwen3-1.7b'  # fine-tuned Qwen3-1.7B, 71/71 on eval_cases.json; what ai_summary uses by default (SUMMARY_MODEL_ID)
CANDIDATE_ID = None  # e.g. 'Qwen/Qwen3-4B-Instruct-2507'; compared with eval_summary.py --model; or your fine-tuned repo
PROXY_PORT = 8000
# Reserved ngrok domain: the public URL stays the same on every run, so .env never changes.
NGROK_DOMAIN = 'unbranded-genotypical-aurea.ngrok-free.dev'
# Xet transfers can stall on Kaggle with no log output; plain HTTPS downloads are reliable.
os.environ['HF_HUB_DISABLE_XET'] = '1'
try:
    HF_TOKEN = UserSecretsClient().get_secret('HF_TOKEN')
except Exception:
    HF_TOKEN = None

# model id -> (port, GPU index)
SERVERS = {MODEL_ID: (8001, '0')}
if CANDIDATE_ID:
    SERVERS[CANDIDATE_ID] = (8002, '1')
processes = globals().get('processes', {})


def served_models(port):
    try:
        return [m['id'] for m in requests.get(f'http://127.0.0.1:{port}/v1/models', timeout=2).json()['data']]
    except (requests.RequestException, ValueError, KeyError):
        return []


def log_path(model_id):
    return f"/kaggle/working/vllm_{model_id.replace('/', '_')}.log"


def start(model_id):
    """Download (with a progress bar) then launch vLLM on its own GPU; reuse it if already serving."""
    port, gpu = SERVERS[model_id]
    if model_id in served_models(port) or (model_id in processes and processes[model_id].poll() is None):
        return
    from huggingface_hub import snapshot_download
    snapshot_download(model_id, token=HF_TOKEN)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, **({'HF_TOKEN': HF_TOKEN} if HF_TOKEN else {}))
    processes[model_id] = subprocess.Popen([
        'python', '-m', 'vllm.entrypoints.openai.api_server', '--model', model_id, '--port', str(port),
        '--dtype', 'half',                    # T4 has no bfloat16
        '--max-model-len', '16384',           # one 18k-character chunk + schema output fits comfortably
        '--gpu-memory-utilization', '0.92',
        '--enable-prefix-caching',            # chunks share the system prompt
        '--max-num-seqs', '8',                # parallel chunks are batched together
    ], env=env, start_new_session=True, stdout=open(log_path(model_id), 'w'), stderr=subprocess.STDOUT)


with ThreadPoolExecutor(max_workers=len(SERVERS)) as pool:
    list(pool.map(start, SERVERS))

started = time.time()
while True:
    pending = [m for m, (port, _) in SERVERS.items() if m not in served_models(port)]
    if not pending:
        break
    for model_id in pending:
        process = processes.get(model_id)
        if process is not None and process.poll() is not None:
            raise RuntimeError(f'{model_id} exited:\n' + open(log_path(model_id)).read()[-4000:])
    if time.time() - started > 1200:
        raise RuntimeError(f'not ready after 20 min: {pending}; see the vllm_*.log files in /kaggle/working')
    for model_id in pending:  # last log line tells the stage: load weights / compile / graph capture
        lines = [l for l in open(log_path(model_id), errors='replace').read().splitlines() if l.strip()]
        print(f'[{time.time() - started:>5.0f}s] {model_id}: {lines[-1][-140:] if lines else "starting..."}', flush=True)
    time.sleep(30)

# One proxy routes each request to the server that serves its "model"; unknown models go to MODEL_ID.
BACKENDS = {port: served_models(port) for port, _ in SERVERS.values()}
if not served_models(PROXY_PORT):
    proxy = FastAPI()

    @proxy.get('/v1/models')
    async def list_models():
        data = []
        async with httpx.AsyncClient() as client:
            for port in BACKENDS:
                try:
                    data += (await client.get(f'http://127.0.0.1:{port}/v1/models', timeout=5)).json()['data']
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
        return {'object': 'list', 'data': data}

    @proxy.post('/v1/{path:path}')
    async def forward(path: str, request: Request):
        body = await request.body()
        model = json.loads(body or b'{}').get('model')
        if not any(model in ids for ids in BACKENDS.values()):  # a server was swapped since the last lookup
            BACKENDS.update({p: served_models(p) for p in BACKENDS})
        port = next((p for p, ids in BACKENDS.items() if model in ids), SERVERS[MODEL_ID][0])
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                reply = await client.post(f'http://127.0.0.1:{port}/v1/{path}', content=body,
                                          headers={'content-type': 'application/json'})
            except httpx.ConnectError:  # the vLLM process behind this port died; its log says why
                return Response(json.dumps({'error': f'{model} is not running on port {port}'}), 503,
                                media_type='application/json')
        return Response(reply.content, reply.status_code, media_type=reply.headers.get('content-type'))

    threading.Thread(target=uvicorn.run, args=(proxy,), daemon=True,
                     kwargs=dict(host='127.0.0.1', port=PROXY_PORT, log_level='warning')).start()
    while not served_models(PROXY_PORT):
        time.sleep(1)

# Passed per process rather than saved with set_auth_token: newer agents reject re-saving the same token.
conf.get_default().auth_token = UserSecretsClient().get_secret('NGROK_AUTH_TOKEN')


def open_tunnel(port):
    """Point the reserved domain at a local port, replacing this kernel's earlier tunnel."""
    for tunnel in ngrok.get_tunnels():
        if NGROK_DOMAIN in tunnel.public_url:
            ngrok.disconnect(tunnel.public_url)
    # The reserved-domain option name depends on the ngrok agent: endpoints API uses `url`,
    # older tunnel APIs use `domain` or `hostname`.
    error = None
    for option in (dict(url=f'https://{NGROK_DOMAIN}'), dict(domain=NGROK_DOMAIN), dict(hostname=NGROK_DOMAIN)):
        try:
            return ngrok.connect(port, **option).public_url
        except PyngrokNgrokHTTPError as exc:
            error = exc
    raise error


if not any(NGROK_DOMAIN in t.public_url for t in ngrok.get_tunnels()):
    open_tunnel(PROXY_PORT)
print('=' * 60)
print(f'Ready in {time.time() - started:.0f}s. Serving https://{NGROK_DOMAIN}/v1 ->', served_models(PROXY_PORT))
print(f'.env: SUMMARY_LLM_URL=https://{NGROK_DOMAIN}/v1   SUMMARY_MODEL_ID={MODEL_ID}')
print('=' * 60)

# Cell 3 — keep the notebook alive while serving (only needed for "Save & Run All")
# while served_models(PROXY_PORT): time.sleep(60)

# Diagnose — a model missing from /v1/models: is its process alive, and what did it log last?
# for m, (port, gpu) in SERVERS.items():
#     p = processes.get(m)
#     print(m, 'port', port, 'GPU', gpu, '| exit code:', None if p is None else p.poll(), '| serving:', served_models(port))
#     print('\n'.join(open(log_path(m), errors='replace').read().splitlines()[-25:]), '\n' + '-' * 60)
# !nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv

# Cell 4 (optional) — swap only the candidate, e.g. to your fine-tuned repo; the main model keeps running.
# import signal
# NEW_CANDIDATE = 'phamthanhfd/contract-summary-qwen3-1.7b'
# if CANDIDATE_ID in processes and processes[CANDIDATE_ID].poll() is None:
#     os.killpg(processes[CANDIDATE_ID].pid, signal.SIGTERM); processes[CANDIDATE_ID].wait(120); time.sleep(5)
# SERVERS.pop(CANDIDATE_ID, None); CANDIDATE_ID = NEW_CANDIDATE; SERVERS[CANDIDATE_ID] = (8002, '1')
# start(CANDIDATE_ID)
# while CANDIDATE_ID not in served_models(8002): time.sleep(15)
# BACKENDS[8002] = served_models(8002)   # the running proxy reads BACKENDS on every request
# print('candidate ready:', BACKENDS[8002])
