# Bật toàn bộ dự án Contract Guard AI bằng một lệnh:
#   powershell -ExecutionPolicy Bypass -File .\run-all.ps1            (bật tất cả, mở trình duyệt)
#   powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -NoGpu     (không bật GPU runtime cổng 8010)
#   powershell -ExecutionPolicy Bypass -File .\run-all.ps1 -Logs      (bật xong thì xem log)
# Thứ tự: Docker Desktop -> PostgreSQL (chờ healthy) -> Neo4j, Qdrant, Fabric -> các dịch vụ Django -> GPU runtime.
param(
    [switch]$NoGpu,
    [switch]$NoBrowser,
    [switch]$Logs
)
$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath '.env')) { throw 'Chưa có file .env ở thư mục gốc dự án.' }

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Wait-Until([scriptblock]$Check, [int]$Seconds, [string]$What) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try { if (& $Check) { return $true } } catch { }
        Start-Sleep -Seconds 2
    }
    Write-Warning "$What chưa sẵn sàng sau $Seconds giây."
    return $false
}
function Http-Ok([string]$Url) {
    try { (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode -lt 500 } catch {
        $code = $_.Exception.Response.StatusCode.value__
        return ($code -and $code -lt 500)
    }
}

# 1. Docker Desktop
Step 'Docker Desktop'
& docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $dockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerExe)) { throw 'Không tìm thấy Docker Desktop.' }
    Start-Process $dockerExe
    $ok = Wait-Until { & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null; $LASTEXITCODE -eq 0 } 240 'Docker Desktop'
    if (-not $ok) { throw 'Docker Desktop không khởi động được.' }
}
Write-Host 'Docker đang chạy.'

$compose = @('compose')

# 2. PostgreSQL trước, chờ healthy để các dịch vụ Django không lỗi kết nối
Step 'PostgreSQL'
& docker @compose up -d --no-build postgres
if ($LASTEXITCODE -ne 0) { throw 'Không bật được PostgreSQL.' }
$ok = Wait-Until { (& docker inspect --format '{{.State.Health.Status}}' contract_postgres) -eq 'healthy' } 120 'PostgreSQL'
if (-not $ok) { throw 'PostgreSQL không healthy.' }
Write-Host 'PostgreSQL healthy.'

# 3. Neo4j, Qdrant, Fabric và các dịch vụ ứng dụng
Step 'Neo4j, Qdrant, Hyperledger Fabric, web, AI, workflow, blockchain'
$services = @(
    'neo4j', 'qdrant',
    'orderer.example.com', 'peer0.org1.example.com', 'fabric-chaincode', 'fabric-gateway',
    'web', 'ai', 'summary-worker', 'workflow-service', 'blockchain-service', 'ledger-worker'
)
# Chaincode và gateway chạy từ image dựng sẵn; máy chưa có image thì dựng một lần (cần mạng).
foreach ($pair in @(@('contract-chaincode-local:latest', 'fabric-chaincode'), @('contract-fabric-gateway-local:latest', 'fabric-gateway'))) {
    & docker image inspect $pair[0] 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Dựng image $($pair[1])..."
        & docker @compose build $pair[1]
        if ($LASTEXITCODE -ne 0) { throw "Không dựng được image $($pair[1])." }
    }
}
& docker @compose up -d --no-build --no-deps @services
if ($LASTEXITCODE -ne 0) { throw 'Không bật được các dịch vụ Docker.' }
# Docker tự bật lại container khi khởi động, có thể trước lúc PostgreSQL sẵn sàng; khởi động lại các dịch vụ dùng CSDL.
& docker restart riskdl_web riskdl_ai riskdl_summary_worker workflow_service blockchain_service contract_ledger_worker | Out-Null

# 4. GPU runtime trên Windows (Surya, VietOCR, GLiNER, BGE) - cổng 8010
if (-not $NoGpu) {
    Step 'GPU runtime (cổng 8010)'
    if (Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue) {
        Write-Host 'GPU runtime đã chạy sẵn.'
    } else {
        New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'runtime\logs') -Force | Out-Null
        $runtimeArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $PSScriptRoot 'start-a3-inference.ps1') + '"'))
        Start-Process powershell.exe -ArgumentList $runtimeArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
            -RedirectStandardOutput 'runtime\logs\inference-out.log' -RedirectStandardError 'runtime\logs\inference-error.log' | Out-Null
        Write-Host 'Đã bật GPU runtime chạy ngầm; log: runtime\logs\inference-error.log'
    }
}

# 5. Chờ và kiểm tra
Step 'Kiểm tra dịch vụ'
$checks = [ordered]@{
    'Web (8000)'            = 'http://localhost:8000/login/'
    'Workflow (8003)'       = 'http://localhost:8003/'
    'Blockchain (8002)'     = 'http://localhost:8002/'
    'Fabric Gateway (5000)' = 'http://localhost:5000/health'
    'Qdrant (6335)'         = 'http://localhost:6335/'
    'Neo4j (7475)'          = 'http://localhost:7475/'
}
if (-not $NoGpu) { $checks['GPU runtime (8010)'] = 'http://localhost:8010/rag/health' }
$summary = foreach ($name in $checks.Keys) {
    $wait = if ($name -like 'GPU*') { 180 } else { 90 }
    $up = Wait-Until { Http-Ok $checks[$name] } $wait $name
    [pscustomobject]@{ 'Dịch vụ' = $name; 'Trạng thái' = $(if ($up) { 'OK' } else { 'CHƯA LÊN' }) }
}
$summary | Format-Table -AutoSize
& docker ps --format 'table {{.Names}}\t{{.Status}}'

Write-Host "`nỨng dụng: http://localhost:8000/" -ForegroundColor Green
Write-Host 'Lưu ý: mô hình Qwen3-8B chạy trên Kaggle; mở notebook và điền địa chỉ ngrok vào .env nếu cần phân tích rủi ro / hỏi đáp.'
Write-Host 'Xem log: .\show-logs.ps1   |   Tắt: docker compose stop'
if (-not $NoBrowser) { Start-Process 'http://localhost:8000/' }
if ($Logs) { & (Join-Path $PSScriptRoot 'show-logs.ps1') }
