param(
    [string]$Python = '',
    [int]$Port = 8010,
    [switch]$AllowLowMemory, # Compatibility only; startup has no free-RAM threshold.
    [switch]$AllowLowDiskSpace
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# Start the runtime without an artificial free-RAM threshold.
$taskSystemDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'"
if ([double]$taskSystemDrive.FreeSpace -lt 4GB) {
    if (-not $AllowLowDiskSpace) { throw 'Local inference not started: system drive needs at least 4 GB free for runtime headroom.' }
    Write-Warning 'Explicit low-disk startup using existing offline checkpoints.'
}
if (-not $Python) {
    $Python = Join-Path $PSScriptRoot 'runtime\windows-env\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { $Python = "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe" }
}
if (-not (Test-Path -LiteralPath $Python)) { throw 'Specify the existing model Python using -Python.' }
$taskTemp = Join-Path $PSScriptRoot 'runtime\tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Offline by default: never reinstall torch or redownload existing models.
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
# Model cache inside the project (runtime\hf_cache), never another project's folder.
$env:HF_HOME = Join-Path $PSScriptRoot 'runtime\hf_cache'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HUGGINGFACE_HUB_CACHE = $env:HF_HUB_CACHE
$env:BGE_LOCAL_CACHE = $env:HF_HUB_CACHE
$env:RAG_TEXT_DEVICE = 'cuda'
$env:RAG_STREAM_CHECKPOINTS = '1'
# Drop idle model weights after two minutes; set before startup to override.
if (-not $env:RAG_IDLE_UNLOAD_SECONDS) { $env:RAG_IDLE_UNLOAD_SECONDS = '120' }
if (-not $env:A3_DOCKER_LOG_CONTAINER) { $env:A3_DOCKER_LOG_CONTAINER = 'riskdl_web' }
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
$env:SURYA_INFERENCE_AUTOSTART = 'False'
$env:SURYA_PAGE_GENERATION_TIMEOUT = '0'
$env:SURYA_REQUEST_GENERATION_TIMEOUT = '0'
$taskModels = Join-Path $PSScriptRoot 'runtime\models'
$env:GLINER_MODEL_PATH = Join-Path $taskModels 'gliner-relex-multi-v1.0'
$env:NLI_MODEL_PATH = Join-Path $taskModels 'nli-deberta-v3-xsmall'
if (Test-Path -LiteralPath "$taskModels\bge-m3\model.safetensors") { $env:BGE_MODEL_PATH = "$taskModels\bge-m3" }
$taskLlama = Get-ChildItem -LiteralPath "$taskModels\llama" -Filter llama-server.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($taskLlama -and (Test-Path -LiteralPath "$taskModels\surya\surya-2.gguf") -and (Test-Path -LiteralPath "$taskModels\surya\surya-2-mmproj.gguf")) {
    $env:LLAMA_CPP_BINARY = $taskLlama.FullName
    $env:PATH = "$($taskLlama.DirectoryName);$PSScriptRoot\runtime\windows-env\Lib\site-packages\torch\lib;$env:PATH"
    $env:SURYA_INFERENCE_BACKEND = 'llamacpp'
    $env:SURYA_GGUF_LOCAL_MODEL_PATH = "$taskModels\surya\surya-2.gguf"
    $env:SURYA_GGUF_LOCAL_MMPROJ_PATH = "$taskModels\surya\surya-2-mmproj.gguf"
    $env:SURYA_INFERENCE_PARALLEL = '2'
    # Each request uses at most about 2,700 tokens; a larger context only reserves memory.
    $env:SURYA_INFERENCE_CTX_SIZE = '16384'
    $env:SURYA_INFERENCE_KEEP_ALIVE = 'True'
    $env:SURYA_INFERENCE_AUTOSTART = 'False'
    $env:SURYA_INFERENCE_URL = 'http://127.0.0.1:8011/v1'
    # The runtime owns the process so it can recover crashes and release VRAM.
    $env:SURYA_MANAGED_BACKEND = '1'
    $env:SURYA_EXCLUSIVE_GPU = '1'
}
& $Python -B -c "import torch,transformers,surya,fastapi,uvicorn; print('Existing runtime:',torch.__version__,'CUDA:',torch.cuda.is_available())"
if ($LASTEXITCODE -ne 0) { throw 'Existing inference runtime is incomplete; no dependencies were installed.' }
& $Python -B -m uvicorn ai.ai_extract.views.inference_app:app --host 0.0.0.0 --port $Port --workers 1
