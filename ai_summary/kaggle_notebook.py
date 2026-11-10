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

# Cell 2 — start the main model on GPU 0 and, on GPU 1, a candidate or a second copy IN PARALLEL, behind one URL.
# Startup is a one-off per session: weight download, then vLLM compile + CUDA graph capture (1-3 min per
# model on T4). Both models load at the same time, so the wait is the slower one, not the sum.
# CANDIDATE_ID = None runs a second copy of the main model, which about doubles what can be processed at once.
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

# name -> (model id, port, GPU index). A candidate takes the second GPU; otherwise it runs a second copy of the
# main model, and the proxy sends each request to the copy with the fewest requests in progress.
GPU_COUNT = len(subprocess.run(['nvidia-smi', '-L'], capture_output=True, text=True).stdout.splitlines())
SERVERS = {'main': (MODEL_ID, 8001, '0')}
if GPU_COUNT > 1:
    SERVERS['second'] = (CANDIDATE_ID or MODEL_ID, 8002, '1')
processes = globals().get('processes', {})
in_flight = globals().get('in_flight', {})


def served_models(port):
    try:
        return [m['id'] for m in requests.get(f'http://127.0.0.1:{port}/v1/models', timeout=2).json()['data']]
    except (requests.RequestException, ValueError, KeyError):
        return []


def log_path(name):
    return f'/kaggle/working/vllm_{name}.log'


def start(name):
    """Download then launch vLLM on its own GPU; reuse it if already serving."""
    model_id, port, gpu = SERVERS[name]
    if model_id in served_models(port) or (name in processes and processes[name].poll() is None):
        return
    from huggingface_hub import snapshot_download
    snapshot_download(model_id, token=HF_TOKEN)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, **({'HF_TOKEN': HF_TOKEN} if HF_TOKEN else {}))
    processes[name] = subprocess.Popen([
        'python', '-m', 'vllm.entrypoints.openai.api_server', '--model', model_id, '--port', str(port),
        '--dtype', 'half',                    # T4 has no bfloat16
        '--max-model-len', '16384',           # one chunk + schema output fits comfortably
        '--gpu-memory-utilization', '0.92',
        '--enable-prefix-caching',            # chunks share the system prompt
        '--max-num-seqs', '8',                # parallel chunks are batched together
    ], env=env, start_new_session=True, stdout=open(log_path(name), 'w'), stderr=subprocess.STDOUT)


with ThreadPoolExecutor(max_workers=len(SERVERS)) as pool:
    list(pool.map(start, SERVERS))

started = time.time()
while True:
    pending = [name for name, (model_id, port, _) in SERVERS.items() if model_id not in served_models(port)]
    if not pending:
        break
    for name in pending:
        process = processes.get(name)
        if process is not None and process.poll() is not None:
            raise RuntimeError(f'{name} exited:\n' + open(log_path(name)).read()[-4000:])
    if time.time() - started > 1200:
        raise RuntimeError(f'not ready after 20 min: {pending}; see the vllm_*.log files in /kaggle/working')
    for name in pending:  # last log line tells the stage: load weights / compile / graph capture
        lines = [l for l in open(log_path(name), errors='replace').read().splitlines() if l.strip()]
        print(f'[{time.time() - started:>5.0f}s] {name}: {lines[-1][-140:] if lines else "starting..."}', flush=True)
    time.sleep(30)


def backend_ports(model):
    """Ports serving this model, asked fresh so a swapped or dead server is noticed; the main model if unknown."""
    ports = [port for model_id, port, _ in SERVERS.values() if model_id == model and model in served_models(port)]
    return ports or [SERVERS['main'][1]]


if not served_models(PROXY_PORT):
    proxy = FastAPI()

    @proxy.get('/v1/models')
    async def list_models():
        data = {}
        async with httpx.AsyncClient() as client:
            for _, port, _ in SERVERS.values():
                try:
                    for entry in (await client.get(f'http://127.0.0.1:{port}/v1/models', timeout=5)).json()['data']:
                        data[entry['id']] = entry
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
        return {'object': 'list', 'data': list(data.values())}

    @proxy.post('/v1/{path:path}')
    async def forward(path: str, request: Request):
        body = await request.body()
        model = json.loads(body or b'{}').get('model')
        port = min(backend_ports(model), key=lambda p: in_flight.get(p, 0))
        in_flight[port] = in_flight.get(port, 0) + 1
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                reply = await client.post(f'http://127.0.0.1:{port}/v1/{path}', content=body,
                                          headers={'content-type': 'application/json'})
        except httpx.ConnectError:  # the vLLM process behind this port died; its log says why
            return Response(json.dumps({'error': f'{model} is not running on port {port}'}), 503,
                            media_type='application/json')
        finally:
            in_flight[port] -= 1
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


def watch_tunnel():
    """ngrok sessions drop without warning; reopen the tunnel after two failed checks in a row."""
    failures = 0
    while True:
        time.sleep(60)
        try:
            ok = requests.get(f'https://{NGROK_DOMAIN}/v1/models', timeout=20,
                              headers={'ngrok-skip-browser-warning': '1'}).status_code == 200
        except requests.RequestException:
            ok = False
        failures = 0 if ok else failures + 1
        if failures >= 2:
            print('tunnel down, reopening', flush=True)
            try:
                ngrok.kill()
                open_tunnel(PROXY_PORT)
                failures = 0
            except Exception as error:  # keep watching: the next round tries again
                print('tunnel reopen failed:', error, flush=True)


if not any(t.name == 'watch-tunnel' and t.is_alive() for t in threading.enumerate()):
    threading.Thread(target=watch_tunnel, daemon=True, name='watch-tunnel').start()
print('=' * 60)
print(f'Ready in {time.time() - started:.0f}s. Serving https://{NGROK_DOMAIN}/v1 ->', served_models(PROXY_PORT))
print(f'.env: SUMMARY_LLM_URL=https://{NGROK_DOMAIN}/v1   SUMMARY_MODEL_ID={MODEL_ID}')
print('=' * 60)

# Cell 3 — keep the session running and restart a vLLM server that died. It never returns: to run another cell,
# interrupt it (the servers, proxy and tunnel keep running) and run it again afterwards.
# With "Save Version -> Save & Run All" the notebook runs without an open browser tab, until Kaggle's session limit.
# while True:
#     for name, (model_id, port, _) in SERVERS.items():
#         if model_id not in served_models(port) and name in processes and processes[name].poll() is not None:
#             print(f'{name} stopped (exit {processes[name].poll()}), restarting', flush=True)
#             start(name)
#     print(time.strftime('%H:%M:%S'), {name: bool(served_models(port)) for name, (_, port, _) in SERVERS.items()}, flush=True)
#     time.sleep(300)

# Diagnose — a model missing from /v1/models: is its process alive, and what did it log last?
# for name, (model_id, port, gpu) in SERVERS.items():
#     p = processes.get(name)
#     print(name, model_id, 'port', port, 'GPU', gpu, '| exit code:', None if p is None else p.poll(), '| serving:', served_models(port))
#     print('\n'.join(open(log_path(name), errors='replace').read().splitlines()[-25:]), '\n' + '-' * 60)
# !nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv

# Cell 4 (optional) — put another model on the second GPU, e.g. a new fine-tune; the main model keeps running.
# The proxy looks up who serves a model on each request, so nothing else needs updating.
# import signal
# NEW_CANDIDATE = 'phamthanhfd/contract-summary-qwen3-1.7b'
# if 'second' in processes and processes['second'].poll() is None:
#     os.killpg(processes['second'].pid, signal.SIGTERM); processes['second'].wait(120); time.sleep(5)
# SERVERS['second'] = (NEW_CANDIDATE, 8002, '1')
# start('second')
# while NEW_CANDIDATE not in served_models(8002): time.sleep(15)
# print('candidate ready:', served_models(8002))
